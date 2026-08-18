"""RuleBasedMatcher — 不依赖 LLM 的确定性匹配 Baseline(B0)。

生成与 GroundTruthEvaluator 兼容的 MatchPrediction:
- 硬约束(HardRuleValidator)不过 → fit=LOW,低分
- 方向匹配(target_roles 关键词) + 技能覆盖(requirements 命中率)
- "优先/加分" 条件不满足、短板技能命中 → 降档与风险记录

这是 C3 GeneralAgentExecutor 的规则回退实现,也是 C2 阶段能立即产出
指标的唯一 predictor。评分规则公开透明,便于与人工 Ground Truth 对照。
"""

from __future__ import annotations

from lhas.job.models import (
    CandidateProfile,
    CareerGoal,
    HardConstraintResult,
    JobRecord,
    MatchPrediction,
)
from lhas.job.rules import HardRuleValidator, WEAK_SKILL_SIGNALS, matches_any_skill

FIT_HIGH = "HIGH"
FIT_MEDIUM = "MEDIUM"
FIT_LOW = "LOW"

# 方向匹配关键词(title 级)
_DIRECTION_KEYWORDS: list[tuple[list[str], float]] = [
    (["Agent", "智能体", "LLM Agent"], 1.0),
    (["AI 应用", "大模型应用", "AI 产品", "应用开发", "应用研发", "应用工程"], 1.0),
    (["AI 全栈", "全栈"], 1.0),  # 需配合 title 含 AI 判定,见 _direction
    (["AI Coding", "代码生成", "代码分析"], 1.0),
    (["AI 前端"], 1.0),
    (["AI Infra", "算法", "测试开发", "数据分析"], 0.4),
]

_HIGH_CUTOFF = 70.0
_MEDIUM_CUTOFF = 45.0


class RuleBasedMatcher:
    def __init__(self, profile: CandidateProfile, goal: CareerGoal):
        self.profile = profile
        self.goal = goal
        self._hard = HardRuleValidator(profile, goal)

    def predict(self, job: JobRecord) -> MatchPrediction:
        hard: HardConstraintResult = self._hard.validate(job)
        direction = self._direction(job)
        matched, cover = self._skill_coverage(job)
        weak_hits = [r for r in job.requirements if self._is_weak(r)]
        preferred_mismatch = self._preferred_mismatch(job)

        if not hard.passed:
            score = 15.0 + 10.0 * cover
            return MatchPrediction(
                job_id=job.job_id, fit=FIT_LOW, score=round(score, 1),
                evidence=matched, risks=hard.violations,
                hard_constraints_pass=False, should_apply=False, source="rule",
            )

        base = 100.0 * (0.45 + 0.35 * direction + 0.20 * cover)
        score = base - 8.0 * len(weak_hits) - 10.0 * (1 if preferred_mismatch else 0)

        # fit 判定(公开规则)
        if direction >= 1.0 and cover >= 0.5:
            fit = FIT_HIGH
        elif direction >= 1.0:
            fit = FIT_MEDIUM
        elif direction >= 0.4:
            fit = FIT_MEDIUM
        else:
            fit = FIT_MEDIUM if cover >= 0.25 else FIT_LOW

        if preferred_mismatch and fit == FIT_HIGH:
            fit = FIT_MEDIUM
        if len(weak_hits) >= 2 and fit == FIT_HIGH:
            fit = FIT_MEDIUM

        risks = list(hard.violations)
        risks += [f"短板:{r}" for r in weak_hits]
        risks += self._unmatched_risks(job, matched)
        if preferred_mismatch:
            risks.append("优先条件(硕士/博士)不满足")
        risks = risks[:4]

        return MatchPrediction(
            job_id=job.job_id, fit=fit, score=round(max(score, 0.0), 1),
            evidence=matched, risks=risks,
            hard_constraints_pass=True,
            should_apply=fit != FIT_LOW,
            source="rule",
        )

    # ---------------------------------------------------------------- bits

    def _direction(self, job: JobRecord) -> float:
        """方向匹配:title 优先;title 无信号时看 job_type。"""
        t = job.title
        if any(k in t for k in ["Agent", "智能体"]):
            return 1.0
        if any(k in t for k in ["AI 应用", "大模型应用", "AI 产品", "应用开发", "应用研发", "应用工程"]):
            return 1.0
        if "AI 全栈" in t or ("全栈" in t and "AI" in t):
            return 1.0
        if any(k in t for k in ["AI Coding", "代码生成", "代码分析"]):
            return 1.0
        if "AI 前端" in t:
            return 1.0
        if any(k in t for k in ["AI Infra", "算法", "测试开发", "数据分析"]):
            return 0.4
        if any(k in (job.job_type or "") for k in ["AI Infra", "Agent 算法"]):
            return 0.4
        return 0.0

    def _skill_coverage(self, job: JobRecord) -> tuple[list[str], float]:
        """requirements 中命中候选人技能的条目(排除"加分:"前缀的软要求)。"""
        hard_reqs = [r for r in job.requirements if not r.startswith(("加分:", "优先"))]
        matched = [r for r in hard_reqs if self._matches_profile(r)]
        if not hard_reqs:
            return [], 1.0
        return matched, len(matched) / len(hard_reqs)

    def _preferred_mismatch(self, job: JobRecord) -> bool:
        if "硕士优先" in job.degree_required and self.profile.education.degree != "硕士":
            return True
        if "博士优先" in job.degree_required and self.profile.education.degree != "博士":
            return True
        return False

    def _matches_profile(self, requirement: str) -> bool:
        return matches_any_skill(requirement, self.profile.skill_flat)

    def _is_weak(self, requirement: str) -> bool:
        return any(sig in requirement for sig in WEAK_SKILL_SIGNALS)

    def _unmatched_risks(self, job: JobRecord, matched: list[str]) -> list[str]:
        return [f"未匹配要求:{r}" for r in job.requirements if r not in matched][:2]
