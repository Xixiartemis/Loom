"""检测器测试:过期判定与重复岗位检测(docs/11)。"""

from pathlib import Path

from lhas.job.detectors import DuplicateDetector, ExpirationValidator
from lhas.job.models import load_job_dataset

DATASET = Path(__file__).resolve().parents[1] / "benchmarks" / "job-v0.1"


def test_expiration_validator_on_locked_as_of():
    ds = load_job_dataset(DATASET)
    validator = ExpirationValidator(as_of=ds.as_of_date)
    statuses = {job.job_id: validator.check(job) for job in ds.ordered_jobs}
    assert statuses["JD-029"] == "EXPIRED"
    assert statuses["JD-030"] == "ACTIVE"
    # 其余全部 ACTIVE
    assert sum(1 for s in statuses.values() if s == "EXPIRED") == 1


def test_expiration_matches_ground_truth():
    ds = load_job_dataset(DATASET)
    validator = ExpirationValidator(as_of=ds.as_of_date)
    for job in ds.ordered_jobs:
        assert validator.check(job) == ds.labels[job.job_id].expiration_status, job.job_id


def test_duplicate_detector_finds_dup_029():
    ds = load_job_dataset(DATASET)
    detector = DuplicateDetector(ds.ordered_jobs)
    pairs = detector.find_duplicate_pairs()
    pair_ids = [(a, b) for a, b, _ in pairs]
    assert ("JD-029", "JD-030") in pair_ids or ("JD-030", "JD-029") in pair_ids
    assert len(pairs) == 1, f"unexpected duplicate pairs: {pairs}"


def test_duplicate_groups_match_ground_truth():
    ds = load_job_dataset(DATASET)
    detector = DuplicateDetector(ds.ordered_jobs)
    groups = detector.groups()
    gt_groups = {g for g in (l.duplicate_group for l in ds.labels.values()) if g}
    assert gt_groups == {"dup-029"}
    detected_members = {jid for ids in groups.values() for jid in ids}
    gt_members = {jid for jid, l in ds.labels.items() if l.duplicate_group}
    assert detected_members == gt_members
