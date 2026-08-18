"""Job 数据集契约测试:加载真实 benchmarks/job-v0.1(Phase C0/C1)。"""

import json
from pathlib import Path

import pytest

from lhas.job.models import fit_distribution, labels_status, load_job_dataset

DATASET = Path(__file__).resolve().parents[1] / "benchmarks" / "job-v0.1"


@pytest.fixture(scope="module")
def ds():
    return load_job_dataset(DATASET)


def test_dataset_loads_30_jobs(ds):
    assert len(ds.jobs) == 30
    assert len(ds.labels) == 30


def test_manifest_composition(ds):
    assert ds.manifest["dataset_id"] == "JOB-V0.1"
    assert ds.manifest["composition"]["total_jobs"] == 30
    assert fit_distribution(ds) == {"HIGH": 10, "MEDIUM": 10, "LOW": 10}


def test_labels_are_draft_pending_human_review(ds):
    assert labels_status(ds) == {"DRAFT": 30}
    # every label carries the full review contract fields
    for lab in ds.labels.values():
        assert lab.hard_constraints_pass in (True, False)
        assert lab.expected_fit in ("HIGH", "MEDIUM", "LOW")
        assert lab.should_apply in (True, False)
        assert lab.expiration_status in ("ACTIVE", "EXPIRED")


def test_all_trap_types_present(ds):
    """6 类陷阱全部覆盖(用户规范)。"""
    hard_fail = [jid for jid, l in ds.labels.items() if not l.hard_constraints_pass]
    assert len(hard_fail) == 10
    expired = [jid for jid, l in ds.labels.items() if l.expiration_status == "EXPIRED"]
    dups = {g for g in (l.duplicate_group for l in ds.labels.values()) if g}
    assert expired == ["JD-029"]
    assert dups == {"dup-029"}
    assert ds.labels["JD-030"].duplicate_group == "dup-029"


def test_job_type_mix_present(ds):
    types = {j.job_type for j in ds.jobs.values()}
    for required in ["AI Agent", "AI 应用", "AI 全栈", "AI Coding", "AI 前端", "纯前端", "普通后端", "Agent 算法", "AI Infra", "测试开发"]:
        assert required in types, required


def test_candidate_three_way_separation():
    """Resume / CandidateProfile / CareerGoal 三者分离(docs/05)。"""
    profile = json.loads((DATASET / "candidate" / "candidate_profile_v1.json").read_text(encoding="utf-8"))
    goal = json.loads((DATASET / "candidate" / "career_goal_v1.json").read_text(encoding="utf-8"))
    resume = (DATASET / "candidate" / "resume_v1.md").read_text(encoding="utf-8")
    assert profile["education"]["graduation_year"] == 2026
    assert "AI Application / Agent Systems" in goal["preferred_direction"]
    assert "pure model training" in goal["avoid_primary_direction"]
    assert "张一诺" in resume
    # profile 与 resume 事实一致(spot check)
    assert "React" in profile["skill_flat"]
    assert "React" in resume


def test_generated_jobs_match_script_source():
    """生成脚本幂等:重新生成 == 已提交内容(dataset 可复现)。"""
    import importlib.util
    import json

    spec = importlib.util.spec_from_file_location(
        "gen", Path(__file__).resolve().parents[1] / "scripts" / "generate_job_dataset.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for row in mod.JDS:
        jid = row[0]
        committed = (DATASET / "jobs" / f"{jid}.json").read_text(encoding="utf-8")
        rebuilt = json.dumps({
            "job_id": row[0], "company": row[1], "title": row[2], "location": row[3],
            "remote": row[4], "source": row[5], "url": row[6], "posted_date": row[7],
            "expires_at": row[8], "job_type": row[9], "degree_required": row[10],
            "graduate_year_required": row[11], "experience_required": row[12],
            "jd_text": row[13], "requirements": row[14], "responsibilities": row[15],
        }, ensure_ascii=False, indent=2) + "\n"
        assert committed == rebuilt, f"{jid} drifted from generator"
