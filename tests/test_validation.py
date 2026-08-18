"""Validator tests (docs/06 — judge only, never modify)."""

import asyncio

from lhas.domain.enums import ExecutionStatus
from lhas.domain.models import Attempt, Task
from lhas.executors.protocol import ExecutionResult
from lhas.validation import AlwaysPassValidator, NeverPassValidator, RuleValidator


def _task():
    return Task(project_id="p", title="t", objective="o")


def _attempt(n=1):
    return Attempt(run_id="r", attempt_number=n)


async def _validate(validator, output):
    result = ExecutionResult(status=ExecutionStatus.SUCCESS, output=output)
    return await validator.validate(task=_task(), attempt=_attempt(), result=result)


def test_rule_validator_rejects_empty_output():
    vr = asyncio.run(_validate(RuleValidator(), output=""))
    assert vr.passed is False
    names = [c.name for c in vr.checks]
    assert "output_non_empty" in names
    assert "empty" in vr.evidence.lower()


def test_rule_validator_requires_marker():
    vr = asyncio.run(_validate(RuleValidator(expected_markers=["expected:ok"]), output="wrong answer"))
    assert vr.passed is False
    assert "expected:ok" in vr.evidence
    vr2 = asyncio.run(_validate(RuleValidator(expected_markers=["expected:ok"]), output="expected:ok"))
    assert vr2.passed is True
    assert "ok" in vr2.evidence


def test_rule_validator_does_not_mutate_result():
    result = ExecutionResult(status=ExecutionStatus.SUCCESS, output="hello")
    asyncio.run(RuleValidator().validate(task=_task(), attempt=_attempt(), result=result))
    assert result.output == "hello"
    assert result.status is ExecutionStatus.SUCCESS


def test_validation_result_records_stdout_and_evidence():
    vr = asyncio.run(_validate(RuleValidator(expected_markers=["ok"]), output="all ok"))
    assert vr.stdout == "all ok"
    assert vr.attempt_id == "r" or vr.attempt_id  # attempt id captured
    assert vr.level == "V2_RULE"


def test_doubles():
    assert asyncio.run(_validate(AlwaysPassValidator(), output="")) .passed is True
    assert asyncio.run(_validate(NeverPassValidator(), output="anything")).passed is False
