"""RecoveryPolicy tests (docs/08 V0 default policy)."""

import asyncio

from lhas.domain.enums import AttemptStatus, FailureClass, FailureType, RecoveryActionType
from lhas.domain.models import Attempt, Task
from lhas.failure import FailureReport
from lhas.recovery import DefaultRecoveryPolicy


def _task(max_attempts=3):
    return Task(project_id="p", title="t", objective="o", max_attempts=max_attempts)


def _attempt(n):
    return Attempt(run_id="r", attempt_number=n, status=AttemptStatus.FAILED)


_TYPE_TO_CLASS = {
    FailureType.TIMEOUT: FailureClass.EXECUTION,
    FailureType.EXECUTOR_CRASH: FailureClass.EXECUTION,
    FailureType.NETWORK_ERROR: FailureClass.EXECUTION,
    FailureType.TOOL_ERROR: FailureClass.EXECUTION,
    FailureType.MISSING_CONTEXT: FailureClass.CONTEXT,
    FailureType.STALE_CONTEXT: FailureClass.CONTEXT,
    FailureType.CONTEXT_CONFLICT: FailureClass.CONTEXT,
    FailureType.CONTEXT_OVERLOAD: FailureClass.CONTEXT,
    FailureType.EMPTY_RESULT: FailureClass.DATA,
    FailureType.MISSING_REQUIRED_FIELD: FailureClass.DATA,
    FailureType.APPROVAL_REQUIRED: FailureClass.ACTION,
    FailureType.UNKNOWN: FailureClass.UNKNOWN,
}


def _report(failure_type=FailureType.UNKNOWN):
    return FailureReport(
        attempt_id="a", failure_type=failure_type, failure_class=_TYPE_TO_CLASS[failure_type],
        evidence="ev", summary="sum", confidence=0.5, suggested_recovery="retry",
    )


async def _decide(task, n, ft=FailureType.UNKNOWN, history=None):
    policy = DefaultRecoveryPolicy()
    return await policy.decide(
        task=task, attempt=_attempt(n), failure_report=_report(ft),
        attempt_number=n, max_attempts=task.max_attempts, history=history or [],
    )


def test_attempt1_retry_with_failure_context():
    action = asyncio.run(_decide(_task(), 1))
    assert action.action_type is RecoveryActionType.RETRY_WITH_FAILURE_CONTEXT
    assert action.attempt_to == 2
    assert "failure_evidence" in action.added_context


def test_attempt2_retry_with_expanded_context():
    action = asyncio.run(_decide(_task(), 2))
    assert action.action_type is RecoveryActionType.RETRY_WITH_EXPANDED_CONTEXT
    assert action.attempt_to == 3
    assert "relevant_history" in action.added_context


def test_attempt3_escalates():
    action = asyncio.run(_decide(_task(max_attempts=3), 3))
    assert action.action_type is RecoveryActionType.ESCALATE
    assert action.attempt_to is None


def test_missing_context_supplies_information():
    action = asyncio.run(_decide(_task(), 1, FailureType.MISSING_CONTEXT))
    assert action.action_type is RecoveryActionType.RETRY_WITH_FAILURE_CONTEXT
    assert "missing_context" in action.added_context


def test_context_conflict_escalates():
    action = asyncio.run(_decide(_task(), 1, FailureType.CONTEXT_CONFLICT))
    assert action.action_type is RecoveryActionType.ESCALATE


def test_timeout_controlled_retry():
    action = asyncio.run(_decide(_task(), 2, FailureType.TIMEOUT))
    assert action.action_type is RecoveryActionType.RETRY_WITH_FAILURE_CONTEXT


def test_approval_required_goes_to_gate():
    action = asyncio.run(_decide(_task(), 1, FailureType.APPROVAL_REQUIRED))
    assert action.action_type is RecoveryActionType.HUMAN_APPROVAL


def test_no_infinite_retry():
    policy = DefaultRecoveryPolicy()
    task = _task(max_attempts=5)
    for n in [1, 2, 3, 4]:
        action = asyncio.run(_decide(task, n))
        assert action.action_type is not RecoveryActionType.ESCALATE
    final = asyncio.run(_decide(task, 5))
    assert final.action_type is RecoveryActionType.ESCALATE
