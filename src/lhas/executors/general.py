"""GeneralAgentExecutor(docs/04, Phase C3)— 通用 Agent 执行器。

第一阶段只做一件事:JD + Candidate + Career Goal → Match Analysis
(fit / evidence / risks / score),固定 30 JD 离线推理,不做搜索。

配置全部外置(env,不修改 LHAS Core):
  LHAS_JOB_LLM_BASE_URL  (默认 https://api.deepseek.com/v1)
  LHAS_JOB_LLM_API_KEY   (必填;缺失时明确报错,提示改用 --predictor rule)
  LHAS_JOB_LLM_MODEL     (默认 deepseek-chat)
  LHAS_JOB_LLM_TIMEOUT   (默认 60s)

未配置模型时,RuleBasedMatcher 是唯一的运行路径(规则回退,不烧 token)。
"""

from __future__ import annotations

import json
import os
import asyncio
import time
import urllib.error
import urllib.request
from typing import Any, Optional

from lhas.domain.enums import ExecutionStatus
from lhas.executors.protocol import ExecutionRequest, ExecutionResult
from lhas.job.models import CandidateProfile, CareerGoal, JobRecord, MatchPrediction


class LLMClient:
    """极简 OpenAI-compatible chat completions 客户端(标准库,零新依赖)。"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 60.0,
        temperature: float = 0.0,
    ):
        self.base_url = base_url.rstrip("/")
        if not self.base_url.endswith("/chat/completions"):
            self.base_url += "/chat/completions"
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.temperature = temperature
        self.last_usage: dict[str, Any] = {}
        self.last_latency_ms: int = 0

    def chat_json(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "response_format": {"type": "json_object"},
        }
        req = urllib.request.Request(
            self.base_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        started = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"LLM API HTTP {exc.code}: {exc.read().decode('utf-8', 'ignore')[:300]}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"LLM API unreachable: {exc.reason}") from exc
        self.last_latency_ms = int((time.monotonic() - started) * 1000)
        raw_usage = body.get("usage") or {}
        self.last_usage = {
            "input_tokens": raw_usage.get("prompt_tokens", raw_usage.get("input_tokens")),
            "output_tokens": raw_usage.get("completion_tokens", raw_usage.get("output_tokens")),
            "total_tokens": raw_usage.get("total_tokens"),
            "latency_ms": self.last_latency_ms,
        }
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise RuntimeError(f"unexpected LLM response shape: {str(body)[:300]}") from exc
        return _parse_json_object(content)


def _parse_json_object(content: str) -> dict[str, Any]:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start, end = content.find("{"), content.rfind("}")
        if start >= 0 and end > start:
            return json.loads(content[start : end + 1])
        raise ValueError(f"LLM output is not JSON: {content[:300]}")


def llm_config_from_env() -> dict[str, Any]:
    """读取外部配置;缺失 api_key 时抛错(不允许静默降级)。"""
    api_key = os.environ.get("LHAS_JOB_LLM_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "LHAS_JOB_LLM_API_KEY is not set — configure a provider first, "
            "or use --predictor rule (deterministic baseline, no tokens)."
        )
    return {
        "base_url": os.environ.get("LHAS_JOB_LLM_BASE_URL", "https://api.deepseek.com/v1"),
        "api_key": api_key,
        "model": os.environ.get("LHAS_JOB_LLM_MODEL", "deepseek-chat"),
        "timeout": float(os.environ.get("LHAS_JOB_LLM_TIMEOUT", "60")),
    }


_MATCH_PROMPT = """你是岗位匹配分析器。基于给定的 Job Description、候选人档案与职业目标,
输出 JSON(不要输出任何其他文字):

{{
  "fit": "HIGH|MEDIUM|LOW",
  "score": <0-100 整数>,
  "hard_constraints_pass": true|false,
  "evidence": ["<匹配证据,必须来自 JD 或简历中的事实>"],
  "risks": ["<风险点>"],
  "should_apply": true|false
}}

判定规则:
1. hard_constraints_pass: 学历/毕业年份/地点(偏好深圳/广州/远程,remote 岗位视为匹配)/
   核心技能/经验年限是否满足;不满足任何一个即 false。
2. fit: 结合 hard 约束、目标方向匹配度、技能重合度给 HIGH/MEDIUM/LOW。
3. evidence 只允许引用 JD requirements 与候选人简历中实际存在的事实,
   禁止编造简历或 JD 中不存在的信息。
4. should_apply: hard 通过且 fit != LOW 且岗位未过期时为 true。

=== Job Description ===
{job_json}

=== Candidate Profile ===
{profile_json}

=== Career Goal ===
{goal_json}
"""


class GeneralAgentExecutor:
    """通用 Agent 执行器(Phase C3):LLM 结构化输出 Match Analysis。

    实现 AgentExecutor Protocol;每 Attempt 由 factory 新建实例,无状态。
    """

    name = "GeneralAgentExecutor"

    def __init__(self, client: Optional[LLMClient] = None):
        self.client = client

    def predict(self, job: JobRecord, profile: CandidateProfile, goal: CareerGoal) -> MatchPrediction:
        if self.client is None:
            raise RuntimeError("no LLM client configured — set LHAS_JOB_LLM_API_KEY or use --predictor rule")
        messages = [
            {"role": "system", "content": "你是严格的 JSON 输出器。"},
            {"role": "user", "content": _MATCH_PROMPT.format(
                job_json=json.dumps(job.model_dump(), ensure_ascii=False, indent=2),
                profile_json=json.dumps(profile.model_dump(), ensure_ascii=False, indent=2),
                goal_json=json.dumps(goal.model_dump(), ensure_ascii=False, indent=2),
            )},
        ]
        raw = self.client.chat_json(messages)
        return MatchPrediction(
            job_id=job.job_id,
            fit=str(raw.get("fit", "LOW")).upper(),
            score=float(raw.get("score", 0)),
            evidence=[str(e) for e in raw.get("evidence", [])],
            risks=[str(r) for r in raw.get("risks", [])],
            hard_constraints_pass=bool(raw.get("hard_constraints_pass", False)),
            should_apply=bool(raw.get("should_apply", False)),
            source="llm",
        )

    # ------------------------------------------------- AgentExecutor Protocol

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        job_raw = request.task.get("job") or {}
        job = JobRecord(**job_raw)
        profile_raw = request.context.get("candidate_profile")
        goal_raw = request.context.get("career_goal")
        # ContextBuilder serializes sections as text; accept both native dicts
        # and JSON strings so the Runtime remains the sole context assembler.
        if profile_raw is None and isinstance(request.context.get("profile"), str):
            combined = json.loads(request.context["profile"])
            profile_raw = combined.get("candidate_profile")
            goal_raw = combined.get("career_goal")
        if isinstance(profile_raw, str):
            profile_raw = json.loads(profile_raw)
        if isinstance(goal_raw, str):
            goal_raw = json.loads(goal_raw)
        profile = CandidateProfile(**(profile_raw or {}))
        goal = CareerGoal(**(goal_raw or {}))
        prediction = await asyncio.to_thread(self.predict, job, profile, goal)
        usage = {
            "model": self.client.model if self.client else None,
            "provider": "llm",
            "source": "llm",
            **(self.client.last_usage if self.client else {}),
        }
        return ExecutionResult(
            status=ExecutionStatus.SUCCESS,
            output=json.dumps(prediction.model_dump(), ensure_ascii=False),
            usage=usage,
        )

    async def resume(self, request: ExecutionRequest) -> ExecutionResult:
        return await self.execute(request)

    async def cancel(self, run_id: str) -> None:
        return None

    async def status(self, run_id: str) -> dict[str, Any]:
        return {"run_id": run_id, "executor": self.name, "state": "idle"}


def make_llm_predictor(dataset) -> callable:  # noqa: A003
    """构造 (job) -> MatchPrediction 的 LLM predictor(bench.py 使用)。"""
    cfg = llm_config_from_env()
    client = LLMClient(**cfg)
    executor = GeneralAgentExecutor(client=client)

    def predict(job: JobRecord) -> MatchPrediction:
        return executor.predict(job, dataset.profile, dataset.goal)

    return predict
