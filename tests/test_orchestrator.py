"""Orchestrator scenario tests A–E (Phase A acceptance matrix).

Every test asserts:
1. the terminal status of Task / Run / Attempt,
2. the exact event chain (or required subsequence),
3. durability: rows survive a fresh database connection,
4. no acceptance-criteria lowering.
"""

import asyncio

from lhas.domain.enums import AttemptStatus, EventType, ExecutionStatus, RunStatus, TaskStatus
from lhas.domain.models import Run, Task
from lhas.executors.mock import MockConfig, MockExecutor, MockScenario
from lhas.executors.protocol import ExecutionRequest, ExecutionResult
from lhas.orchestrator import Orchestrator, RetryAction
from lhas.persistence.database import Database
from lhas.persistence.event_store import EventStore
from lhas.persistence.repositories import AttemptRepository, RunRepository, TaskRepository
from tests.conftest import chain_of

SUCCESS_CHAIN = [
    "TASK_CREATED", "TASK_STARTED", "RUN_CREATED", "RUN_STARTED",
    "ATTEMPT_STARTED", "CONTEXT_BUILT", "EXECUTOR_STARTED",
    "EXECUTOR_COMPLETED", "ATTEMPT_COMPLETED", "RUN_COMPLETED", "TASK_COMPLETED",
]

FAIL_ONCE_CHAIN = [
    "TASK_CREATED", "TASK_STARTED", "RUN_CREATED", "RUN_STARTED",
    "ATTEMPT_STARTED", "CONTEXT_BUILT", "EXECUTOR_STARTED",
    "EXECUTOR_FAILED", "ATTEMPT_FAILED", "RETRY_SCHEDULED",
    "ATTEMPT_STARTED", "CONTEXT_BUILT", "EXECUTOR_STARTED",
    "EXECUTOR_COMPLETED", "ATTEMPT_COMPLETED", "RUN_COMPLETED", "TASK_COMPLETED",
]


class ScriptedExecutor:
    """Stateless, deterministic executor driven by attempt_number.

    script: {1: "crash", 2: "success", "default": "success"}
    actions: success | failure | timeout | crash
    """

    name = "ScriptedExecutor"

    def __init__(self, script: dict):
        self.script = script

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        n = request.context.get("attempt_number", request.attempt_number)
        action = self.script.get(n, self.script.get("default", "success"))
        if action == "success":
            return ExecutionResult(status=ExecutionStatus.SUCCESS, output=f"ok-{n}", duration_ms=1)
        if action == "failure":
            return ExecutionResult(status=ExecutionStatus.FAILURE, error_type="ExecutionFailure", error_message=f"fail-{n}", duration_ms=1)
        if action == "timeout":
            await asyncio.sleep(30)
            return ExecutionResult(status=ExecutionStatus.SUCCESS, output="late", duration_ms=1)
        if action == "crash":
            raise RuntimeError(f"crash-{n}")
        raise ValueError(f"unknown action {action}")

    async def resume(self, request): return await self.execute(request)
    async def cancel(self, run_id): return None
    async def status(self, run_id): return {}


def _orchestrator(db, factory):
    return Orchestrator(db, executor_factory=factory)


def _events(db, task_id):
    return EventStore(db).list_for_task(task_id)


def test_A_success_path(make_task, make_orchestrator, db):
    task = make_task(title="success-path", max_attempts=3)
    orchestrator = make_orchestrator(scenario=MockScenario.SUCCESS)
    run = asyncio.run(orchestrator.execute_task(task.id))

    assert run.status is RunStatus.COMPLETED
    assert TaskRepository(db).get(task.id).status is TaskStatus.COMPLETED
    attempts = AttemptRepository(db).list_for_run(run.id)
    assert len(attempts) == 1
    assert attempts[0].status is AttemptStatus.COMPLETED
    assert chain_of(db, task.id) == SUCCESS_CHAIN


def test_B_fail_once_then_success(make_task, db):
    task = make_task(title="fail-once-pass", max_attempts=3)
    orchestrator = _orchestrator(db, lambda: MockExecutor(MockConfig(scenario=MockScenario.FAIL_ONCE, fail_times=1)))
    run = asyncio.run(orchestrator.execute_task(task.id))

    assert run.status is RunStatus.COMPLETED
    assert TaskRepository(db).get(task.id).status is TaskStatus.COMPLETED
    attempts = AttemptRepository(db).list_for_run(run.id)
    assert [a.status for a in attempts] == [AttemptStatus.FAILED, AttemptStatus.COMPLETED]
    assert [a.attempt_number for a in attempts] == [1, 2]
    assert chain_of(db, task.id) == FAIL_ONCE_CHAIN

    # RETRY_SCHEDULED carries the Phase A deterministic action
    retry_events = [e for e in _events(db, task.id) if e.event_type is EventType.RETRY_SCHEDULED]
    assert len(retry_events) == 1
    assert retry_events[0].payload["action"] == RetryAction.RETRY_WITH_FAILURE_CONTEXT
    assert retry_events[0].payload["next_attempt"] == 2


def test_C_timeout_escalates(make_task, db):
    task = make_task(title="timeout", max_attempts=3, timeout_seconds=0.1)
    orchestrator = _orchestrator(db, lambda: MockExecutor(MockConfig(scenario=MockScenario.TIMEOUT, sleep_seconds=30.0)))
    run = asyncio.run(orchestrator.execute_task(task.id))

    assert run.status is RunStatus.ESCALATED
    assert TaskRepository(db).get(task.id).status is TaskStatus.ESCALATED
    attempts = AttemptRepository(db).list_for_run(run.id)
    assert [a.status for a in attempts] == [AttemptStatus.TIMED_OUT] * 3
    chain = chain_of(db, task.id)
    assert chain.count("ATTEMPT_TIMED_OUT") == 3
    assert chain.count("EXECUTOR_FAILED") == 3
    assert chain.count("RETRY_SCHEDULED") == 2
    for e in _events(db, task.id):
        if e.event_type is EventType.EXECUTOR_FAILED:
            assert e.payload["reason"] == "timeout"


def test_C2_timeout_then_recover(make_task, db):
    """Timeout is recoverable: attempt 2 (after a timed-out attempt 1) succeeds."""
    task = make_task(title="timeout-recover", max_attempts=3, timeout_seconds=0.1)
    orchestrator = _orchestrator(db, lambda: ScriptedExecutor({1: "timeout", "default": "success"}))
    run = asyncio.run(orchestrator.execute_task(task.id))

    assert run.status is RunStatus.COMPLETED, (
        f"chain={chain_of(db, task.id)} attempts="
        f"{[(a.attempt_number, a.status.value, a.error_type, a.error_message) for a in AttemptRepository(db).list_for_run(run.id)]}"
    )
    attempts = AttemptRepository(db).list_for_run(run.id)
    assert [a.status for a in attempts] == [AttemptStatus.TIMED_OUT, AttemptStatus.COMPLETED]
    chain = chain_of(db, task.id)
    assert chain.count("ATTEMPT_TIMED_OUT") == 1
    assert chain.count("RETRY_SCHEDULED") == 1
    assert chain[-1] == "TASK_COMPLETED"


def test_D_crash_escalates(make_task, db):
    task = make_task(title="crash", max_attempts=3)
    orchestrator = _orchestrator(db, lambda: MockExecutor(MockConfig(scenario=MockScenario.CRASH)))
    run = asyncio.run(orchestrator.execute_task(task.id))

    assert run.status is RunStatus.ESCALATED
    assert TaskRepository(db).get(task.id).status is TaskStatus.ESCALATED
    attempts = AttemptRepository(db).list_for_run(run.id)
    assert [a.status for a in attempts] == [AttemptStatus.CRASHED] * 3
    chain = chain_of(db, task.id)
    assert chain.count("ATTEMPT_CRASHED") == 3
    for e in _events(db, task.id):
        if e.event_type is EventType.EXECUTOR_FAILED:
            assert e.payload["reason"] == "crash"
            assert e.payload["error_type"] == "RuntimeError"


def test_D2_crash_then_recover(make_task, db):
    """Crash is recoverable: a later attempt succeeds after a crash."""
    task = make_task(title="crash-recover", max_attempts=3)
    orchestrator = _orchestrator(db, lambda: ScriptedExecutor({1: "crash", "default": "success"}))
    run = asyncio.run(orchestrator.execute_task(task.id))

    assert run.status is RunStatus.COMPLETED
    attempts = AttemptRepository(db).list_for_run(run.id)
    assert [a.status for a in attempts] == [AttemptStatus.CRASHED, AttemptStatus.COMPLETED]
    chain = chain_of(db, task.id)
    assert chain.count("ATTEMPT_CRASHED") == 1
    assert chain[-1] == "TASK_COMPLETED"


def test_E_three_failures_escalate(make_task, db):
    task = make_task(title="three-fail-escalate", max_attempts=3)
    orchestrator = _orchestrator(db, lambda: MockExecutor(MockConfig(scenario=MockScenario.FAIL_ALWAYS)))
    run = asyncio.run(orchestrator.execute_task(task.id))

    assert run.status is RunStatus.ESCALATED
    assert TaskRepository(db).get(task.id).status is TaskStatus.ESCALATED
    attempts = AttemptRepository(db).list_for_run(run.id)
    assert [a.status for a in attempts] == [AttemptStatus.FAILED] * 3
    chain = chain_of(db, task.id)
    assert chain.count("ATTEMPT_FAILED") == 3
    assert chain.count("RETRY_SCHEDULED") == 2
    assert chain[-2:] == ["RUN_ESCALATED", "TASK_ESCALATED"]

    # deterministic V0 policy actions: failure-context -> expanded-context -> escalate
    actions = [e.payload["action"] for e in _events(db, task.id) if e.event_type is EventType.RETRY_SCHEDULED]
    assert actions == [RetryAction.RETRY_WITH_FAILURE_CONTEXT, RetryAction.RETRY_WITH_EXPANDED_CONTEXT]
    escalated = [e for e in _events(db, task.id) if e.event_type is EventType.TASK_ESCALATED]
    assert escalated[0].payload["reason"] == "max attempts reached"


def test_durability_across_connections(make_task, db, tmp_path):
    """Every entity written during a run survives a fresh DB connection."""
    task = make_task(title="durable", max_attempts=2)
    orch = Orchestrator(db, executor_factory=lambda: MockExecutor(MockConfig(scenario=MockScenario.FAIL_ONCE)))
    asyncio.run(orch.execute_task(task.id))

    # Reload the file with a brand-new Database handle.
    db2 = Database(db.engine.url.database)
    db2.init_db()
    t2 = TaskRepository(db2).get(task.id)
    assert t2 is not None and t2.status is TaskStatus.COMPLETED
    runs = RunRepository(db2).list_for_task(task.id)
    assert len(runs) == 1 and runs[0].status is RunStatus.COMPLETED
    attempts = AttemptRepository(db2).list_for_run(runs[0].id)
    assert len(attempts) == 2
    assert attempts[0].status is AttemptStatus.FAILED
    assert attempts[1].status is AttemptStatus.COMPLETED
    events = EventStore(db2).list_for_task(task.id)
    assert len(events) >= len(FAIL_ONCE_CHAIN)
    assert [e.event_type.value for e in events] == FAIL_ONCE_CHAIN
    db2.close()


def test_attempt_context_snapshot_recorded(make_task, make_orchestrator, db):
    task = make_task(title="snapshot", max_attempts=2)
    orchestrator = make_orchestrator(scenario=MockScenario.FAIL_ONCE)
    run = asyncio.run(orchestrator.execute_task(task.id))
    attempts = AttemptRepository(db).list_for_run(run.id)
    for a in attempts:
        assert a.context_snapshot_id is not None
        assert a.context_snapshot_id.startswith("ctx-")
    built = [e for e in _events(db, task.id) if e.event_type is EventType.CONTEXT_BUILT]
    assert len(built) == 2
    assert built[0].payload["context_snapshot_id"] == attempts[0].context_snapshot_id


def test_task_must_exist(db):
    orch = Orchestrator(db, executor_factory=lambda: MockExecutor())
    try:
        asyncio.run(orch.execute_task("missing"))
        assert False, "expected KeyError"
    except KeyError:
        pass


def test_running_task_rejected(make_task, make_orchestrator, db):
    task = make_task(title="already-running", max_attempts=3)
    repo = TaskRepository(db)
    task.status = TaskStatus.RUNNING
    repo.update(task)
    orch = make_orchestrator()
    try:
        asyncio.run(orch.execute_task(task.id))
        assert False, "expected ValueError"
    except ValueError:
        pass
