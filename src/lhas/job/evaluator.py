"""GroundTruthEvaluator — 预测与人工 Ground Truth 的逐项比对(docs/11, docs/09)。

不修改任何预测;只输出比对结果。证据 grounded 判定:
预测证据项能被 JD requirements / 候选人技能 / GT positive_evidence 中的
任一事实(子串)支撑 → 有依据;否则计入 hallucination。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from lhas.job.models import GroundTruthLabel, JobDataset, JobRecord, MatchPrediction


class EvaluationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    hard_correct: bool
    fit_correct: bool
    apply_correct: bool
    evidence_hit: float = 0.0      # 预测证据中与 GT positive_evidence 一致的占比
    evidence_coverage: float = 0.0  # GT positive_evidence 被预测覆盖的占比
    hallucination: bool = False    # 是否存在无依据证据项
    grounded_ratio: float = 1.0    # 预测证据中被事实支撑的比例


class GroundTruthEvaluator:
    def __init__(self, dataset: JobDataset):
        self.dataset = dataset

    def evaluate(self, pred: MatchPrediction) -> EvaluationResult:
        gt = self.dataset.labels[pred.job_id]
        job = self.dataset.jobs[pred.job_id]

        evidence_hit = self._hit_ratio(pred.evidence, gt.positive_evidence)
        evidence_coverage = self._hit_ratio(gt.positive_evidence, pred.evidence)
        grounded = [e for e in pred.evidence if self._grounded(e, job, gt)]
        grounded_ratio = len(grounded) / len(pred.evidence) if pred.evidence else 1.0

        return EvaluationResult(
            job_id=pred.job_id,
            hard_correct=pred.hard_constraints_pass == gt.hard_constraints_pass,
            fit_correct=pred.fit == gt.expected_fit,
            apply_correct=pred.should_apply == gt.should_apply,
            evidence_hit=round(evidence_hit, 3),
            evidence_coverage=round(evidence_coverage, 3),
            hallucination=grounded_ratio < 1.0,
            grounded_ratio=round(grounded_ratio, 3),
        )

    # ---------------------------------------------------------------- bits

    @staticmethod
    def _hit_ratio(items: list[str], reference: list[str]) -> float:
        if not items and not reference:
            return 1.0  # 双方都无证据 = 完全一致
        if not items:
            return 0.0
        hits = sum(1 for e in items if any(ref in e or e in ref for ref in reference))
        return hits / len(items)

    def _grounded(self, evidence: str, job: JobRecord, gt: GroundTruthLabel) -> bool:
        corpus = list(job.requirements) + list(job.responsibilities)
        corpus += self.dataset.profile.skill_flat
        corpus += gt.positive_evidence
        return any(evidence in e or e in evidence for e in corpus)
