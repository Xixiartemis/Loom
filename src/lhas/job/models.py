"""Job Benchmark 领域模型(benchmarks/job-v0.1 的加载与校验)。

三个身份严格分离(用户规范):
- Resume           = 我有什么(原文,不参与计算)
- CandidateProfile = 系统如何结构化理解我(事实)
- CareerGoal       = 我要去哪(偏好与策略)
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# --------------------------------------------------------------------- entity

class Education(BaseModel):
    model_config = ConfigDict(extra="allow")

    degree: str
    major: str
    school: str
    graduation_year: int


class ProjectInfo(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    role: str
    stack: list[str] = Field(default_factory=list)
    description: str = ""


class ExperienceInfo(BaseModel):
    model_config = ConfigDict(extra="allow")

    company: str
    role: str
    period: str
    duration_months: int = 0
    highlights: list[str] = Field(default_factory=list)


class CandidateProfile(BaseModel):
    """结构化事实:education / skills / projects / experience / awards。"""

    model_config = ConfigDict(extra="allow")

    version: str
    candidate_id: str
    name: str
    education: Education
    skills: dict[str, list[str]] = Field(default_factory=dict)
    skill_flat: list[str] = Field(default_factory=list)
    projects: list[ProjectInfo] = Field(default_factory=list)
    experience: list[ExperienceInfo] = Field(default_factory=list)
    total_experience_months: int = 0
    awards: list[str] = Field(default_factory=list)


class CareerGoal(BaseModel):
    """偏好与策略:target_roles / preferred_direction / avoid / location。"""

    model_config = ConfigDict(extra="allow")

    version: str
    candidate_id: str
    target_roles: list[str] = Field(default_factory=list)
    preferred_direction: str = ""
    avoid_primary_direction: list[str] = Field(default_factory=list)
    location_preference: list[str] = Field(default_factory=list)
    job_nature: list[str] = Field(default_factory=list)
    salary_expectation: str = ""
    notes: str = ""


class JobRecord(BaseModel):
    """结构化 JD(一个岗位快照)。"""

    model_config = ConfigDict(extra="allow")

    job_id: str
    company: str
    title: str
    location: str
    remote: bool = False
    source: str = ""
    url: str = ""
    posted_date: str = ""
    expires_at: str = ""
    job_type: str = ""
    degree_required: str = ""
    graduate_year_required: str = ""
    experience_required: str = ""
    jd_text: str = ""
    requirements: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)

    @property
    def expires_date(self) -> Optional[date]:
        if not self.expires_at:
            return None
        try:
            return date.fromisoformat(self.expires_at)
        except ValueError:
            return None

    @property
    def posted_date_obj(self) -> Optional[date]:
        if not self.posted_date:
            return None
        try:
            return date.fromisoformat(self.posted_date)
        except ValueError:
            return None


class GroundTruthLabel(BaseModel):
    """每份 JD 的基准标注(labels_v1.json,人工确认前为 DRAFT)。"""

    model_config = ConfigDict(extra="allow")

    job_id: str
    hard_constraints_pass: bool
    expected_fit: str  # HIGH / MEDIUM / LOW
    positive_evidence: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    should_apply: bool
    expiration_status: str = "ACTIVE"  # ACTIVE / EXPIRED
    duplicate_group: Optional[str] = None
    status: str = "DRAFT"


class HardConstraintResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool
    violations: list[str] = Field(default_factory=list)


class MatchPrediction(BaseModel):
    """一次匹配预测(规则 matcher 或 AgentExecutor 的输出,统一结构)。"""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    fit: str  # HIGH / MEDIUM / LOW
    score: float
    evidence: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    hard_constraints_pass: bool
    should_apply: bool
    source: str = "unknown"  # rule / llm / ...


# ------------------------------------------------------------------ dataset

class JobDataset(BaseModel):
    """一个锁定的 Benchmark 数据集(manifest + candidate + jobs + labels)。"""

    model_config = ConfigDict(extra="allow")

    manifest: dict[str, Any] = Field(default_factory=dict)
    profile: CandidateProfile
    goal: CareerGoal
    jobs: dict[str, JobRecord] = Field(default_factory=dict)
    labels: dict[str, GroundTruthLabel] = Field(default_factory=dict)

    @property
    def as_of_date(self) -> date:
        raw = self.manifest.get("as_of_date") or self.manifest.get("created_at")
        return date.fromisoformat(raw) if raw else date.today()

    @property
    def ordered_jobs(self) -> list[JobRecord]:
        return [self.jobs[jid] for jid in sorted(self.jobs)]

    def validate_composition(self) -> None:
        """数据集构成校验:数量与 fit 分布符合 manifest 声明。"""
        total = len(self.jobs)
        expected_total = self.manifest.get("composition", {}).get("total_jobs")
        if expected_total is not None and total != expected_total:
            raise ValueError(f"dataset job count {total} != manifest {expected_total}")
        dist = fit_distribution(self)
        for key, fit_value in {
            "expected_fit_high": "HIGH",
            "expected_fit_medium": "MEDIUM",
            "expected_fit_low": "LOW",
        }.items():
            declared = self.manifest.get("composition", {}).get(key)
            if declared is not None and dist.get(fit_value, 0) != declared:
                raise ValueError(f"fit distribution mismatch: {dist} != manifest declaration")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_job_dataset(root: str | Path) -> JobDataset:
    """加载并校验一个 job-v0.1 数据集目录。

    校验(违反即抛错,数据集不可悄悄损坏):
    - manifest / candidate / career_goal / jobs / labels 齐备
    - labels 覆盖全部 job_id,无多余 id
    - 没有重复 job_id
    """
    root = Path(root)
    manifest = _read_json(root / "manifest.json")
    profile = CandidateProfile(**(_read_json(root / "candidate" / "candidate_profile_v1.json")))
    goal = CareerGoal(**(_read_json(root / "candidate" / "career_goal_v1.json")))
    labels_raw = _read_json(root / "ground_truth" / "labels_v1.json")

    jobs: dict[str, JobRecord] = {}
    for jf in sorted((root / "jobs").glob("JD-*.json")):
        job = JobRecord(**_read_json(jf))
        if job.job_id in jobs:
            raise ValueError(f"duplicate job_id in dataset: {job.job_id}")
        jobs[job.job_id] = job

    labels = {jid: GroundTruthLabel(**lab) for jid, lab in labels_raw["labels"].items()}
    missing = set(jobs) - set(labels)
    extra = set(labels) - set(jobs)
    if missing:
        raise ValueError(f"labels missing for jobs: {sorted(missing)}")
    if extra:
        raise ValueError(f"labels without jobs: {sorted(extra)}")

    ds = JobDataset(manifest=manifest, profile=profile, goal=goal, jobs=jobs, labels=labels)
    ds.validate_composition()
    return ds


def fit_distribution(ds: JobDataset) -> dict[str, int]:
    from collections import Counter
    return dict(Counter(l.expected_fit for l in ds.labels.values()))


def labels_status(ds: JobDataset) -> dict[str, int]:
    from collections import Counter
    return dict(Counter(l.status for l in ds.labels.values()))
