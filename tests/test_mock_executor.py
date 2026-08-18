"""MockExecutor behavior tests (docs/04, docs/11 Stage 0)."""

import asyncio

import pytest

from lhas.domain.enums import ExecutionStatus
from lhas.executors.mock import MockConfig, MockExecutor, MockScenario
from lhas.executors.protocol import ExecutionRequest, ExecutionResult


def _request(attempt_number: int = 1, **context) -> ExecutionRequest:
    ctx = {"attempt_number": attempt_number}
    ctx.update(context)
    return ExecutionRequest(
        task_id="t", run_id="r", attempt_id="a", attempt_number=attempt_number,
        task={"title": "demo", "objective": "o"}, context=ctx,
    )


async def _run(scenario: MockScenario, attempt: int = 1, context: dict | None = None, **cfg_kw) -> ExecutionResult:
    executor = MockExecutor(MockConfig(scenario=scenario, **cfg_kw))
    request = _request(attempt)
    if context:
        request.context.update(context)
    return await executor.execute(request)


def test_success_scenario():
    result = asyncio.run(_run(MockScenario.SUCCESS))
    assert result.status is ExecutionStatus.SUCCESS
    assert result.output == "mock-output:demo:attempt-1"
    assert result.error_type is None


def test_fail_once_then_success():
    result1 = asyncio.run(_run(MockScenario.FAIL_ONCE, attempt=1))
    assert result1.status is ExecutionStatus.FAILURE
    assert "attempt 1" in result1.error_message
    result2 = asyncio.run(_run(MockScenario.FAIL_ONCE, attempt=2))
    assert result2.status is ExecutionStatus.SUCCESS


def test_fail_always():
    result = asyncio.run(_run(MockScenario.FAIL_ALWAYS, attempt=9))
    assert result.status is ExecutionStatus.FAILURE


def test_timeout_scenario_never_returns_within_budget():
    async def _go():
        executor = MockExecutor(MockConfig(scenario=MockScenario.TIMEOUT, sleep_seconds=30.0))
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(executor.execute(_request(1)), timeout=0.05)
    asyncio.run(_go())


def test_crash_scenario_raises():
    async def _go():
        executor = MockExecutor(MockConfig(scenario=MockScenario.CRASH))
        with pytest.raises(RuntimeError):
            await executor.execute(_request(1))
    asyncio.run(_go())


def test_recoverable_needs_guidance():
    # attempt 1: fails with MISSING_CONTEXT regardless of context
    r1 = asyncio.run(_run(MockScenario.RECOVERABLE, attempt=1))
    assert r1.status is ExecutionStatus.FAILURE
    assert r1.error_type == "MissingContextError"
    assert "MISSING_CONTEXT" in (r1.error_message or "")
    # attempt 2 without guidance: still fails
    r2 = asyncio.run(_run(MockScenario.RECOVERABLE, attempt=2))
    assert r2.status is ExecutionStatus.FAILURE
    # attempt 2 with recovery guidance: succeeds
    r3 = asyncio.run(_run(MockScenario.RECOVERABLE, attempt=2, context={"recovery_guidance": "MISSING_CONTEXT: supply education level"}))
    assert r3.status is ExecutionStatus.SUCCESS
    assert r3.output == "mock-output-recovered"


def test_bad_first_output_then_expected():
    r1 = asyncio.run(_run(MockScenario.BAD_FIRST_OUTPUT, attempt=1))
    assert r1.status is ExecutionStatus.SUCCESS
    assert "expected" not in (r1.output or "")
    r2 = asyncio.run(_run(MockScenario.BAD_FIRST_OUTPUT, attempt=2))
    assert "expected:ok" in (r2.output or "")


def test_protocol_surface():
    executor = MockExecutor()
    assert executor.name == "MockExecutor"
    assert asyncio.run(executor.cancel("r")) is None
    assert asyncio.run(executor.status("r"))["state"] == "idle"
