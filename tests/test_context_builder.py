"""ContextBuilder tests (docs/05 — minimal, explainable, policy-gated context)."""

from lhas.context_builder import ContextBuilder, ContextPolicy
from lhas.domain.enums import FailureType
from lhas.domain.models import Attempt, Task
from lhas.failure import FailureReport
from lhas.recovery import RecoveryAction


def _task():
    return Task(project_id="p", title="t", objective="build a search agent",
                constraints=["no LLM"], acceptance_criteria=["returns ranked list"])


def _attempt(n):
    return Attempt(run_id="r", attempt_number=n, status="FAILED", error_message="MISSING_CONTEXT: education")


def _report():
    return FailureReport(attempt_id="a", failure_type=FailureType.MISSING_CONTEXT,
                         failure_class="CONTEXT", evidence="education missing",
                         summary="education level missing", confidence=0.95,
                         suggested_recovery="supply education context")


def _action():
    return RecoveryAction(attempt_id="a", action_type="RETRY_WITH_FAILURE_CONTEXT",
                          reason="missing context", context_policy="CP-2",
                          attempt_from=1, attempt_to=2,
                          added_context={"missing_context": "education level missing"})


def test_cp0_has_goal_and_task_only():
    snap = ContextBuilder(policy=ContextPolicy.CP_0).build(task=_task(), attempt_number=1)
    assert snap.policy == "CP-0"
    assert "build a search agent" in snap.sections["goal"]
    assert "no LLM" in snap.sections["task"]
    assert "previous_attempts" not in snap.sections
    assert "profile" not in snap.sections


def test_cp1_adds_profile():
    snap = ContextBuilder(policy=ContextPolicy.CP_1, profile={"education": "MSc"}).build(task=_task(), attempt_number=1)
    assert "MSc" in snap.sections["profile"]


def test_cp2_adds_failure_and_recovery_guidance():
    snap = ContextBuilder(policy=ContextPolicy.CP_2).build(
        task=_task(), attempt_number=2,
        previous_attempts=[_attempt(1)],
        failure_report=_report(),
        recovery_action=_action(),
    )
    assert "previous_attempts" in snap.sections
    assert "MISSING_CONTEXT" in snap.sections["failure"]
    assert "MISSING_CONTEXT" in snap.sections["recovery_guidance"]
    assert "education level missing" in snap.sections["recovery_guidance"]
    raw = snap.raw_text
    assert "build a search agent" in raw
    assert "MISSING_CONTEXT" in raw


def test_snapshot_carries_scope_ids():
    snap = ContextBuilder().build(task=_task(), attempt_number=3, run_id="r1", attempt_id="a3")
    assert snap.run_id == "r1"
    assert snap.attempt_id == "a3"
    assert snap.attempt_number == 3
    assert snap.id


def test_to_executor_context_flat():
    snap = ContextBuilder(policy=ContextPolicy.CP_2).build(task=_task(), attempt_number=1)
    ctx = ContextBuilder().to_executor_context(snap)
    assert ctx["attempt_number"] == 1
    assert "build a search agent" in ctx["goal"]
