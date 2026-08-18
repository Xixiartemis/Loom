"""FailureClassifier tests (docs/07 taxonomy)."""

import asyncio

from lhas.domain.enums import AttemptStatus, ExecutionStatus, FailureClass, FailureType
from lhas.domain.models import Attempt, Task
from lhas.executors.protocol import ExecutionResult
from lhas.failure import RuleFailureClassifier
from lhas.validation import RuleValidator, ValidationResult


def _attempt(status: AttemptStatus, error_message=None, error_type=None):
    return Attempt(run_id="r", attempt_number=1, status=status,
                   error_message=error_message, error_type=error_type)


def _task():
    return Task(project_id="p", title="t", objective="o")


async def _classify(attempt, result=None, validation=None):
    return await RuleFailureClassifier().classify(task=_task(), attempt=attempt, result=result, validation=validation)


def test_timeout_classification():
    report = asyncio.run(_classify(_attempt(AttemptStatus.TIMED_OUT)))
    assert report.failure_type is FailureType.TIMEOUT
    assert report.failure_class is FailureClass.EXECUTION
    assert report.confidence == 1.0
    assert "retry" in report.suggested_recovery.lower()


def test_crash_classification():
    report = asyncio.run(_classify(_attempt(AttemptStatus.CRASHED, error_message="boom", error_type="RuntimeError")))
    assert report.failure_type is FailureType.EXECUTOR_CRASH
    assert report.failure_class is FailureClass.EXECUTION
    assert "boom" in report.evidence


def test_missing_context_classification():
    report = asyncio.run(_classify(
        _attempt(AttemptStatus.FAILED, error_message="MISSING_CONTEXT: candidate education level missing", error_type="MissingContextError")
    ))
    assert report.failure_type is FailureType.MISSING_CONTEXT
    assert report.failure_class is FailureClass.CONTEXT
    assert report.confidence >= 0.9


def test_validation_failure_classification():
    result = ExecutionResult(status=ExecutionStatus.SUCCESS, output="wrong answer")
    validation = asyncio.run(RuleValidator(expected_markers=["expected:ok"]).validate(task=_task(), attempt=_attempt(AttemptStatus.COMPLETED), result=result))
    report = asyncio.run(_classify(_attempt(AttemptStatus.COMPLETED), result=result, validation=validation))
    assert report.failure_type is FailureType.MISSING_REQUIRED_FIELD
    assert report.failure_class is FailureClass.DATA
    assert "validation" in report.evidence


def test_network_error_classification():
    report = asyncio.run(_classify(
        _attempt(AttemptStatus.FAILED, error_message="NETWORK_ERROR: connection reset")
    ))
    assert report.failure_type is FailureType.NETWORK_ERROR
    assert report.failure_class is FailureClass.EXECUTION


def test_unknown_fallback():
    report = asyncio.run(_classify(_attempt(AttemptStatus.FAILED, error_message="something weird")))
    assert report.failure_type is FailureType.UNKNOWN
    assert report.failure_class is FailureClass.UNKNOWN
    assert report.confidence < 0.5
