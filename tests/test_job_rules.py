"""HardRuleValidator 契约测试:规则判定必须与人工 Ground Truth 完全一致。"""

from pathlib import Path

import pytest

from lhas.job.models import load_job_dataset
from lhas.job.rules import HardRuleValidator

DATASET = Path(__file__).resolve().parents[1] / "benchmarks" / "job-v0.1"


@pytest.fixture(scope="module")
def ctx():
    ds = load_job_dataset(DATASET)
    validator = HardRuleValidator(ds.profile, ds.goal)
    return ds, validator


def test_hard_rules_match_ground_truth_for_all_30_jobs(ctx):
    """硬约束是确定性规则,与人工标注必须 100% 一致(不一致即规则 bug)。"""
    ds, validator = ctx
    mismatches = []
    for job in ds.ordered_jobs:
        result = validator.validate(job)
        if result.passed != ds.labels[job.job_id].hard_constraints_pass:
            mismatches.append((job.job_id, ds.labels[job.job_id].hard_constraints_pass, result.violations))
    assert mismatches == [], f"hard-rule/GT mismatches: {mismatches}"


@pytest.mark.parametrize("job_id,reason", [
    ("JD-021", "毕业年份"),
    ("JD-022", "学历"),
    ("JD-023", "地点"),
    ("JD-024", "地点"),
    ("JD-025", "技能"),
    ("JD-026", "学历"),
    ("JD-027", "学历"),
    ("JD-028", "毕业年份"),
    ("JD-029", "经验"),
    ("JD-030", "经验"),
])
def test_trap_jobs_fail_for_documented_reason(ctx, job_id, reason):
    ds, validator = ctx
    result = validator.validate(ds.jobs[job_id])
    assert result.passed is False
    assert any(reason in v for v in result.violations), f"{job_id} violations: {result.violations}"


def test_high_jobs_all_pass_hard(ctx):
    ds, validator = ctx
    high_ids = [jid for jid, l in ds.labels.items() if l.expected_fit == "HIGH"]
    for jid in high_ids:
        assert validator.validate(ds.jobs[jid]).passed, jid
