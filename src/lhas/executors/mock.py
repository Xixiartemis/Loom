"""MockExecutor — deterministic executor for state machine / event / timeout /
crash / fail-once / escalate testing (docs/04, docs/11 Stage 0).

Scenarios:
- SUCCESS:      always succeeds.
- FAIL_ONCE:    fails the first ``fail_times`` attempts, then succeeds.
- FAIL_ALWAYS:  always fails.
- TIMEOUT:      sleeps ``sleep_seconds`` (longer than the task timeout), so the
                orchestrator's asyncio.wait_for cancels it -> TIMED_OUT.
- CRASH:        raises an unexpected exception -> CRASHED.
- RECOVERABLE:  (Phase B) attempt 1 fails with MISSING_CONTEXT; later attempts
                succeed only when the context carries recovery guidance.
- BAD_FIRST_OUTPUT: (Phase B) attempt 1 returns output without the required
                marker, later attempts return the expected output.

Consumes no model quota.
"""

from __future__ import annotations

import asyncio
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from lhas.domain.enums import ExecutionStatus
from lhas.executors.protocol import ExecutionRequest, ExecutionResult


class MockScenario(str, Enum):
    SUCCESS = "SUCCESS"
    FAIL_ONCE = "FAIL_ONCE"
    FAIL_ALWAYS = "FAIL_ALWAYS"
    TIMEOUT = "TIMEOUT"
    CRASH = "CRASH"
    RECOVERABLE = "RECOVERABLE"
    BAD_FIRST_OUTPUT = "BAD_FIRST_OUTPUT"


class MockConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario: MockScenario = MockScenario.SUCCESS
    fail_times: int = Field(default=1, ge=1)
    sleep_seconds: float = Field(default=30.0, gt=0)
    output_template: str = "mock-output:{title}:attempt-{n}"
    recovered_output: str = "mock-output-recovered"
    error_type: str = "ExecutionFailure"
    error_message: str = "mock failure"


class MockExecutor:
    """Stateless w.r.t. attempts: behavior depends on request.context
    (``attempt_number``, ``recovery_guidance``) — never on executor state."""

    name = "MockExecutor"

    def __init__(self, config: MockConfig | None = None):
        self.config = config or MockConfig()

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        scenario = self.config.scenario
        n = int(request.context.get("attempt_number", 1))
        title = request.task.get("title", "task")

        if scenario == MockScenario.TIMEOUT:
            await asyncio.sleep(self.config.sleep_seconds)
            return ExecutionResult(status=ExecutionStatus.SUCCESS, output="unreachable")

        if scenario == MockScenario.CRASH:
            raise RuntimeError("mock executor crash (intentional)")

        if scenario == MockScenario.RECOVERABLE:
            if n == 1:
                return ExecutionResult(
                    status=ExecutionStatus.FAILURE,
                    error_type="MissingContextError",
                    error_message="MISSING_CONTEXT: candidate education level missing",
                    duration_ms=1,
                )
            guidance = request.context.get("recovery_guidance") or ""
            if "MISSING_CONTEXT" in guidance:
                return ExecutionResult(
                    status=ExecutionStatus.SUCCESS,
                    output=self.config.recovered_output,
                    duration_ms=1,
                )
            return ExecutionResult(
                status=ExecutionStatus.FAILURE,
                error_type="MissingContextError",
                error_message="MISSING_CONTEXT: recovery guidance not supplied",
                duration_ms=1,
            )

        if scenario == MockScenario.BAD_FIRST_OUTPUT:
            if n == 1:
                return ExecutionResult(status=ExecutionStatus.SUCCESS, output="wrong answer", duration_ms=1)
            return ExecutionResult(status=ExecutionStatus.SUCCESS, output="expected:ok", duration_ms=1)

        if scenario == MockScenario.FAIL_ONCE and n <= self.config.fail_times:
            return ExecutionResult(
                status=ExecutionStatus.FAILURE,
                error_type=self.config.error_type,
                error_message=f"{self.config.error_message} (attempt {n})",
                duration_ms=1,
            )

        if scenario == MockScenario.FAIL_ALWAYS:
            return ExecutionResult(
                status=ExecutionStatus.FAILURE,
                error_type=self.config.error_type,
                error_message=f"{self.config.error_message} (attempt {n})",
                duration_ms=1,
            )

        output = self.config.output_template.format(title=title, n=n)
        return ExecutionResult(status=ExecutionStatus.SUCCESS, output=output, duration_ms=1)

    async def resume(self, request: ExecutionRequest) -> ExecutionResult:
        # Mock executor keeps no durable state in Phase A; resume == re-execute.
        return await self.execute(request)

    async def cancel(self, run_id: str) -> None:
        return None

    async def status(self, run_id: str) -> dict[str, Any]:
        return {"run_id": run_id, "executor": self.name, "state": "idle"}
