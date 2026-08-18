"""Domain model + enum contract tests (docs/02)."""

import pytest

from lhas.domain.enums import (
    AttemptStatus,
    EventType,
    ExecutionStatus,
    FailureClass,
    FailureType,
    RecoveryActionType,
    RunStatus,
    TaskStatus,
)
from lhas.domain.models import Attempt, Event, Project, Run, Task, json_dumps, json_loads


def test_task_status_enum_covers_docs_states():
    values = {s.value for s in TaskStatus}
    assert {
        "CREATED", "READY", "RUNNING", "VALIDATING", "RECOVERING",
        "COMPLETED", "FAILED", "BLOCKED", "ESCALATED", "CANCELLED",
    } <= values


def test_attempt_status_terminal_states():
    assert AttemptStatus.TIMED_OUT.value == "TIMED_OUT"
    assert AttemptStatus.CRASHED.value == "CRASHED"


def test_execution_status():
    assert ExecutionStatus.SUCCESS.value == "SUCCESS"
    assert ExecutionStatus.FAILURE.value == "FAILURE"
    assert ExecutionStatus.TIMEOUT.value == "TIMEOUT"
    assert ExecutionStatus.CRASH.value == "CRASH"


def test_event_type_catalog_has_phase_a_baseline():
    values = {e.value for e in EventType}
    for required in [
        "TASK_CREATED", "TASK_STARTED", "TASK_COMPLETED", "TASK_ESCALATED",
        "RUN_CREATED", "RUN_STARTED", "RUN_COMPLETED", "RUN_ESCALATED",
        "ATTEMPT_STARTED", "ATTEMPT_COMPLETED", "ATTEMPT_FAILED",
        "ATTEMPT_TIMED_OUT", "ATTEMPT_CRASHED", "CONTEXT_BUILT",
        "EXECUTOR_STARTED", "EXECUTOR_COMPLETED", "EXECUTOR_FAILED",
        "RETRY_SCHEDULED",
    ]:
        assert required in values, required


def test_failure_taxonomy_families():
    assert FailureClass.CONTEXT.value == "CONTEXT"
    assert FailureType.MISSING_CONTEXT.value == "MISSING_CONTEXT"
    assert FailureType.EXECUTOR_CRASH.value == "EXECUTOR_CRASH"
    assert FailureType.UNKNOWN.value == "UNKNOWN"


def test_recovery_action_types():
    assert RecoveryActionType.RETRY_WITH_FAILURE_CONTEXT.value == "RETRY_WITH_FAILURE_CONTEXT"
    assert RecoveryActionType.RETRY_WITH_EXPANDED_CONTEXT.value == "RETRY_WITH_EXPANDED_CONTEXT"
    assert RecoveryActionType.ESCALATE.value == "ESCALATE"


def test_task_defaults():
    task = Task(project_id="p", title="t", objective="o")
    assert task.status is TaskStatus.CREATED
    assert task.max_attempts == 3
    assert task.timeout_seconds == 60.0
    assert task.constraints == []
    assert task.acceptance_criteria == []


def test_task_rejects_extra_fields():
    with pytest.raises(Exception):
        Task(project_id="p", title="t", objective="o", not_a_field=1)


def test_run_defaults():
    run = Run(task_id="t")
    assert run.status is RunStatus.CREATED
    assert run.harness_version == "HV-0.1"
    assert run.executor_type == "MockExecutor"


def test_event_sequence_property():
    event = Event(id=7, event_type=EventType.TASK_CREATED)
    assert event.sequence == 7


def test_json_roundtrip_with_datetimes():
    event = Event(id=1, event_type=EventType.TASK_STARTED, payload={"k": "v"})
    raw = json_dumps(event.model_dump(mode="json"))
    assert json_loads(raw)["event_type"] == "TASK_STARTED"
