"""RuleBasedMatcher 契约测试:确定性 predictor 与人工 Ground Truth 一致。"""

from pathlib import Path

import pytest

from lhas.job.matching import RuleBasedMatcher
from lhas.job.models import load_job_dataset

DATASET = Path(__file__).resolve().parents[1] / "benchmarks" / "job-v0.1"


@pytest.fixture(scope="module")
def ds():
    return load_job_dataset(DATASET)


@pytest.fixture(scope="module")
def matcher(ds):
    return RuleBasedMatcher(ds.profile, ds.goal)


def test_rule_matcher_matches_ground_truth_for_all_30_jobs(ds, matcher):
    """规则 matcher 是人工标注的确定性投影;任何漂移都必须显式处理。"""
    mismatches = []
    for job in ds.ordered_jobs:
        pred = matcher.predict(job)
        gt = ds.labels[job.job_id]
        if pred.fit != gt.expected_fit or pred.hard_constraints_pass != gt.hard_constraints_pass:
            mismatches.append((job.job_id, gt.expected_fit, pred.fit))
    assert mismatches == [], f"matcher/GT mismatches: {mismatches}"


def test_rule_matcher_distribution(ds, matcher):
    fits = {}
    for job in ds.ordered_jobs:
        fits[job.job_id] = matcher.predict(job).fit
    from collections import Counter
    assert Counter(fits.values()) == {"HIGH": 10, "MEDIUM": 10, "LOW": 10}


def test_hard_fail_predictions_never_apply(ds, matcher):
    for job in ds.ordered_jobs:
        pred = matcher.predict(job)
        if not pred.hard_constraints_pass:
            assert pred.fit == "LOW"
            assert pred.should_apply is False
            assert pred.score < 50


def test_evidence_is_grounded_in_jd_or_resume(ds, matcher):
    """规则 matcher 的证据必须来自 JD requirements/候选人技能(可核查)。"""
    corpus = set(ds.profile.skill_flat)
    for job in ds.ordered_jobs:
        pred = matcher.predict(job)
        for ev in pred.evidence:
            assert any(ev in r or r in ev for r in job.requirements) or any(
                ev in s or s in ev for s in corpus
            ), f"{job.job_id} evidence not grounded: {ev}"
