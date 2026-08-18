"""RecoveringOrchestrator tests — the Phase B closed loop
FAIL → CLASSIFY → RECOVER → PASS (docs/01, docs/14 Phase B gate)."""

import asyncio

from lhas.context_builder import ContextBuilder
from lhas.domain.enums import EventType, RunStatus, TaskStatus
from lhas.executors.mock import MockConfig, MockExecutor, MockScenario
from lhas.failure import RuleFailureClassifier
from lhas.orchestrator_v2 import RecoveringOrchestrator
from lhas.persistence.database import Database
from lhas.persistence.event_store import EventStore
from lhas.persistence.phaseb_repos import (
    ContextSnapshotRepository,
    FailureReportRepository,
    RecoveryActionRepository,
    ValidationResultRepository,
)
from lhas.persistence.repositories import AttemptRepository, TaskRepository
from lhas.recovery import DefaultRecoveryPolicy
from lhas.validation import AlwaysPassValidator, RuleValidator
from tests.conftest import chain_of

RECOVER_CHAIN = [
    "EXECUTOR_FAILED", "ATTEMPT_FAILED", "FAILURE_CLASSIFIED",
    "RECOVERY_DECIDED", "RECOVERY_STARTED", "ATTEMPT_STARTED",
    "EXECUTOR_COMPLETED", "ATTEMPT_COMPLETED",
    "VALIDATION_STARTED", "VALIDATION_PASSED", "RUN_COMPLETED", "TASK_COMPLETED",
]


def _v2(db, scenario, *, markers=None, policy="CP-2", validator=None, **kw):
    return RecoveringOrchestrator(
        db,
        executor_factory=lambda: MockExecutor(MockConfig(scenario=scenario)),
        validator=validator or RuleValidator(expected_markers=markers or []),
        classifier=RuleFailureClassifier(),
        recovery_policy=DefaultRecoveryPolicy(context_policy=policy),
        context_builder=ContextBuilder(policy=policy),
        context_policy_version=policy,
        **kw,
    )


def _events(db, task_id):
    return EventStore(db).list_for_task(task_id)


def test_recoverable_fail_classify_recover_pass(make_task, db):
    task = make_task(title="recoverable", max_attempts=3)
    orch = _v2(db, MockScenario.RECOVERABLE)
    run = asyncio.run(orch.execute_task(task.id))

    assert run.status is RunStatus.COMPLETED
    assert TaskRepository(db).get(task.id).status is TaskStatus.COMPLETED
    attempts = AttemptRepository(db).list_for_run(run.id)
    assert [a.status.value for a in attempts] == ["FAILED", "COMPLETED"]
    chain = chain_of(db, task.id)
    it = iter(chain)
    assert all(name in it for name in RECOVER_CHAIN), chain

    # attempt 1: classified MISSING_CONTEXT
    report = FailureReportRepository(db).list_for_attempt(attempts[0].id)[0]
    assert report.failure_type.value == "MISSING_CONTEXT"
    assert attempts[0].failure_type == "MISSING_CONTEXT"
    # recovery action supplies the missing context
    action = RecoveryActionRepository(db).list_for_attempt(attempts[0].id)[0]
    assert action.action_type.value == "RETRY_WITH_FAILURE_CONTEXT"
    assert "missing_context" in action.added_context
    # attempt 2 context carries recovery guidance; mock only succeeds with it
    snapshots = ContextSnapshotRepository(db).list_for_attempt(attempts[1].id)
    assert len(snapshots) == 1
    assert "MISSING_CONTEXT" in snapshots[0].sections.get("recovery_guidance", "")
    assert attempts[1].output == "mock-output-recovered"

    # the FAILURE_CLASSIFIED / RECOVERY_DECIDED events carry payloads
    classified = [e for e in _events(db, task.id) if e.event_type is EventType.FAILURE_CLASSIFIED]
    assert classified[0].payload["failure_type"] == "MISSING_CONTEXT"
    decided = [e for e in _events(db, task.id) if e.event_type is EventType.RECOVERY_DECIDED]
    assert decided[0].payload["action"] == "RETRY_WITH_FAILURE_CONTEXT"


def test_validation_feedback_loop(make_task, db):
    """Executor 'succeeds' but validation fails -> classify -> recover -> pass."""
    task = make_task(title="validation-feedback", max_attempts=3)
    orch = _v2(db, MockScenario.BAD_FIRST_OUTPUT, markers=["expected:ok"])
    run = asyncio.run(orch.execute_task(task.id))

    assert run.status is RunStatus.COMPLETED
    attempts = AttemptRepository(db).list_for_run(run.id)
    assert len(attempts) == 2
    chain = chain_of(db, task.id)
    assert chain.count("VALIDATION_STARTED") == 2
    assert chain.count("VALIDATION_FAILED") == 1
    assert chain.count("VALIDATION_PASSED") == 1
    assert chain.count("FAILURE_CLASSIFIED") == 1
    assert chain.count("RECOVERY_STARTED") == 1

    v1 = ValidationResultRepository(db).list_for_attempt(attempts[0].id)
    assert len(v1) == 1 and v1[0].passed is False
    assert "expected:ok" in (v1[0].evidence or "")
    v2 = ValidationResultRepository(db).list_for_attempt(attempts[1].id)
    assert len(v2) == 1 and v2[0].passed is True

    report = FailureReportRepository(db).list_for_attempt(attempts[0].id)[0]
    assert report.failure_type.value == "MISSING_REQUIRED_FIELD"


def test_unrecoverable_escalates_with_full_logs(make_task, db):
    task = make_task(title="unrecoverable", max_attempts=3)
    orch = _v2(db, MockScenario.FAIL_ALWAYS)
    run = asyncio.run(orch.execute_task(task.id))

    assert run.status is RunStatus.ESCALATED
    attempts = AttemptRepository(db).list_for_run(run.id)
    assert len(attempts) == 3
    chain = chain_of(db, task.id)
    assert chain[-2:] == ["RUN_ESCALATED", "TASK_ESCALATED"]

    # full logs: one FailureReport + one RecoveryAction per attempt
    for a in attempts:
        assert len(FailureReportRepository(db).list_for_attempt(a.id)) == 1
        assert len(RecoveryActionRepository(db).list_for_attempt(a.id)) == 1
        assert a.failure_type is not None
    actions = [RecoveryActionRepository(db).list_for_attempt(a.id)[0].action_type.value for a in attempts]
    assert actions == ["RETRY_WITH_FAILURE_CONTEXT", "RETRY_WITH_EXPANDED_CONTEXT", "ESCALATE"]


def test_passing_validation_never_classifies(make_task, db):
    """No failure -> no classification/recovery events at all."""
    task = make_task(title="clean-pass", max_attempts=3)
    orch = _v2(db, MockScenario.SUCCESS, validator=AlwaysPassValidator())
    run = asyncio.run(orch.execute_task(task.id))
    assert run.status is RunStatus.COMPLETED
    attempts = AttemptRepository(db).list_for_run(run.id)
    assert len(attempts) == 1
    chain = chain_of(db, task.id)
    assert "FAILURE_CLASSIFIED" not in chain
    assert "RECOVERY_DECIDED" not in chain
    assert "VALIDATION_PASSED" in chain


def test_phaseb_persistence_across_connections(make_task, db):
    """Snapshots / validations / reports / actions survive a fresh connection."""
    task = make_task(title="phaseb-durable", max_attempts=3)
    orch = _v2(db, MockScenario.RECOVERABLE)
    run = asyncio.run(orch.execute_task(task.id))
    assert run.status is RunStatus.COMPLETED

    db2 = Database(db.engine.url.database)
    db2.init_db()
    task2 = TaskRepository(db2).get(task.id)
    assert task2.status is TaskStatus.COMPLETED
    attempts = AttemptRepository(db2).list_for_run(run.id)
    assert len(attempts) == 2
    assert attempts[0].failure_type == "MISSING_CONTEXT"
    assert len(ContextSnapshotRepository(db2).list_for_attempt(attempts[0].id)) == 1
    assert len(FailureReportRepository(db2).list_for_attempt(attempts[0].id)) == 1
    assert len(RecoveryActionRepository(db2).list_for_attempt(attempts[0].id)) == 1
    assert len(ValidationResultRepository(db2).list_for_attempt(attempts[1].id)) == 1
    events = EventStore(db2).list_for_task(task.id)
    types = [e.event_type.value for e in events]
    assert "FAILURE_CLASSIFIED" in types and "VALIDATION_PASSED" in types
    db2.close()
