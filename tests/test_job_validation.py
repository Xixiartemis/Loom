"""JobMatchValidator 测试:为 EXP-JOB-002 的 Recovery 提供 FAIL 信号。"""

from pathlib import Path

import pytest

from lhas.job.matching import RuleBasedMatcher
from lhas.job.models import MatchPrediction, load_job_dataset
from lhas.job.validation import JobMatchValidator

DATASET = Path(__file__).resolve().parents[1] / "benchmarks" / "job-v0.1"


@pytest.fixture(scope="module")
def ds():
    return load_job_dataset(DATASET)


def _pred(job_id, fit="HIGH", hard=True, apply=True):
    return MatchPrediction(
        job_id=job_id, fit=fit, score=90.0, evidence=["x"], risks=[],
        hard_constraints_pass=hard, should_apply=apply, source="test",
    )


def test_honest_prediction_passes(ds):
    validator = JobMatchValidator(ds)
    matcher = RuleBasedMatcher(ds.profile, ds.goal)
    pred = matcher.predict(ds.jobs["JD-001"])
    result = validator.validate(pred)
    assert result.passed is True, result.evidence


def test_hard_fail_claimed_pass_is_caught(ds):
    """预测自称 hard pass,但确定性规则判定 hard fail → WRONG_MATCH 信号。"""
    validator = JobMatchValidator(ds)
    result = validator.validate(_pred("JD-021", fit="HIGH", hard=True, apply=True))
    assert result.passed is False
    names = [c.name for c in result.checks]
    assert "hard_constraints_consistent" in names
    failed = [c for c in result.checks if not c.passed]
    assert any(c.name == "hard_constraints_consistent" for c in failed)


def test_high_fit_outside_career_goal_is_caught(ds):
    """JD-013(普通后端)被标 HIGH → 方向冲突(用户示例:WRONG_MATCH)。"""
    validator = JobMatchValidator(ds)
    result = validator.validate(_pred("JD-013", fit="HIGH"))
    assert result.passed is False
    failed = {c.name for c in result.checks if not c.passed}
    assert "direction_conflict" in failed


def test_expired_job_apply_is_caught(ds):
    validator = JobMatchValidator(ds)
    result = validator.validate(_pred("JD-029", fit="MEDIUM", hard=True, apply=True))
    assert result.passed is False
    failed = {c.name for c in result.checks if not c.passed}
    assert "expired_apply" in failed


def test_rule_predictions_pass_validation(ds):
    """规则 matcher 的 30 个预测全部通过 JobMatchValidator(自洽性)。"""
    validator = JobMatchValidator(ds)
    matcher = RuleBasedMatcher(ds.profile, ds.goal)
    failures = []
    for job in ds.ordered_jobs:
        result = validator.validate(matcher.predict(job))
        if not result.passed:
            failures.append((job.job_id, result.evidence))
    assert failures == [], failures
