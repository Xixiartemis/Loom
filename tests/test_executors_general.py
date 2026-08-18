"""GeneralAgentExecutor 测试(Phase C3):配置外置、无 key 明确报错、
结构化输出契约;真实 LLM 调用需要 key,不在 CI 中执行。"""

import pytest

from lhas.domain.enums import ExecutionStatus
from lhas.executors.general import GeneralAgentExecutor, LLMClient, llm_config_from_env, _parse_json_object
from lhas.executors.protocol import ExecutionRequest
from lhas.job.models import load_job_dataset

DATASET = "benchmarks/job-v0.1"


def test_llm_config_missing_key_raises_clearly(monkeypatch):
    monkeypatch.delenv("LHAS_JOB_LLM_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="LHAS_JOB_LLM_API_KEY"):
        llm_config_from_env()


def test_llm_config_reads_env(monkeypatch):
    monkeypatch.setenv("LHAS_JOB_LLM_API_KEY", "sk-test")
    monkeypatch.setenv("LHAS_JOB_LLM_MODEL", "test-model")
    cfg = llm_config_from_env()
    assert cfg["api_key"] == "sk-test"
    assert cfg["model"] == "test-model"
    assert cfg["base_url"] == "https://api.deepseek.com/v1"


def test_parse_json_object_tolerates_fences():
    assert _parse_json_object('{"fit": "HIGH"}') == {"fit": "HIGH"}
    assert _parse_json_object('```json\n{"fit": "MEDIUM"}\n```') == {"fit": "MEDIUM"}
    with pytest.raises(ValueError):
        _parse_json_object("not json at all")


def test_executor_requires_client():
    executor = GeneralAgentExecutor(client=None)
    with pytest.raises(RuntimeError, match="no LLM client"):
        executor.predict(None, None, None)


def test_llm_client_url_construction():
    client = LLMClient(base_url="https://api.example.com/v1", api_key="k", model="m")
    assert client.base_url.endswith("/chat/completions")
    client2 = LLMClient(base_url="https://api.example.com/v1/chat/completions", api_key="k", model="m")
    assert client2.base_url == "https://api.example.com/v1/chat/completions"


def test_executor_protocol_surface():
    executor = GeneralAgentExecutor()
    assert executor.name == "GeneralAgentExecutor"
    import asyncio
    assert asyncio.run(executor.cancel("r")) is None
    assert asyncio.run(executor.status("r"))["state"] == "idle"


def test_execute_without_key_raises(monkeypatch):
    monkeypatch.delenv("LHAS_JOB_LLM_API_KEY", raising=False)
    ds = load_job_dataset(DATASET)
    executor = GeneralAgentExecutor()
    request = ExecutionRequest(
        task_id="t", run_id="r", attempt_id="a", attempt_number=1,
        task={"job": ds.jobs["JD-001"].model_dump()},
        context={"candidate_profile": ds.profile.model_dump(), "career_goal": ds.goal.model_dump()},
    )
    import asyncio
    with pytest.raises(RuntimeError, match="LHAS_JOB_LLM_API_KEY"):
        asyncio.run(executor.execute(request))


def test_fake_llm_endpoint_roundtrip():
    """用一个本地假 server 验证 LLM 输出 → ExecutionResult 的完整链路。"""
    import asyncio
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class FakeHandler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            length = int(self.headers["Content-Length"])
            body = json.loads(self.rfile.read(length))
            assert body["response_format"]["type"] == "json_object"
            payload = json.dumps({
                "choices": [{"message": {"content": json.dumps({
                    "fit": "HIGH", "score": 88, "hard_constraints_pass": True,
                    "evidence": ["React", "LLM API"], "risks": ["生产经验有限"],
                    "should_apply": True,
                })}}],
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):  # silence
            pass

    server = HTTPServer(("127.0.0.1", 0), FakeHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}/v1"
        ds = load_job_dataset(DATASET)
        executor = GeneralAgentExecutor(client=LLMClient(base, "sk-fake", "fake-model"))
        request = ExecutionRequest(
            task_id="t", run_id="r", attempt_id="a", attempt_number=1,
            task={"job": ds.jobs["JD-001"].model_dump()},
            context={"candidate_profile": ds.profile.model_dump(), "career_goal": ds.goal.model_dump()},
        )
        result = asyncio.run(executor.execute(request))
        assert result.status is ExecutionStatus.SUCCESS
        import json as _json
        parsed = _json.loads(result.output)
        assert parsed["fit"] == "HIGH"
        assert parsed["hard_constraints_pass"] is True
        assert "React" in parsed["evidence"]
    finally:
        server.shutdown()
