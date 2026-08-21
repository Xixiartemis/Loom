"""MetricsCalculator — Job Benchmark 核心指标(docs/09_EVAL_PROTOCOL.md)。

阶段 A(本次交付,不依赖 LLM):
- hard_constraint_accuracy
- duplicate_detection_rate
- expired_job_detection_rate
- fit_classification_accuracy
- precision@5 / recall@10 / ranking_quality(NDCG@10)
- evidence_accuracy / hallucination_rate

所有指标在 predictions + ground truth 上确定性计算,与 predictor 无关——
Agent 接入后同一套代码直接出数字。
"""

from __future__ import annotations

import math
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from lhas.job.evaluator import EvaluationResult, GroundTruthEvaluator
from lhas.job.models import JobDataset, MatchPrediction

FIT_GAIN = {"HIGH": 3.0, "MEDIUM": 2.0, "LOW": 1.0}


class MetricsReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    n_jobs: int
    hard_constraint_accuracy: float
    fit_classification_accuracy: float
    precision_at_5: float
    recall_at_10: float
    ranking_quality_ndcg10: float
    evidence_accuracy: float
    evidence_coverage: float
    hallucination_rate: float
    duplicate_detection_rate: float
    expired_job_detection_rate: float
    should_apply_precision: Optional[float] = None
    should_apply_recall: Optional[float] = None


class MetricsCalculator:
    def __init__(self, dataset: JobDataset):
        self.dataset = dataset
        self.evaluator = GroundTruthEvaluator(dataset)

    def compute(self, predictions: list[MatchPrediction]) -> MetricsReport:
        by_job = {p.job_id: p for p in predictions}
        missing = set(self.dataset.jobs) - set(by_job)
        if missing:
            raise ValueError(f"predictions missing for jobs: {sorted(missing)}")

        evals = [self.evaluator.evaluate(by_job[jid]) for jid in sorted(self.dataset.jobs)]

        hard_acc = _mean([e.hard_correct for e in evals])
        fit_acc = _mean([e.fit_correct for e in evals])
        evidence_acc = _mean([e.evidence_hit for e in evals])
        evidence_cov = _mean([e.evidence_coverage for e in evals])
        hallucination = _mean([0.0 if e.grounded_ratio >= 1.0 else 1.0 for e in evals])

        ranked = sorted(predictions, key=lambda p: p.score, reverse=True)
        top5 = ranked[:5]
        top10 = ranked[:10]
        relevant = [jid for jid, gt in self.dataset.labels.items() if gt.should_apply]
        rel_set = set(relevant)

        precision_at_5 = len([p for p in top5 if p.job_id in rel_set]) / len(top5) if top5 else 0.0
        recall_at_10 = len([p for p in top10 if p.job_id in rel_set]) / len(rel_set) if rel_set else 0.0

        ndcg = self._ndcg_at_10(ranked)
        duplicate_rate = self._duplicate_detection_rate()
        expired_rate = self._expired_detection_rate(evals)

        # should_apply 精确率/召回率(与文档 Eval 指标对应)
        tp = sum(1 for p in predictions if p.job_id in rel_set and p.should_apply)
        pred_apply = sum(1 for p in predictions if p.should_apply)
        apply_precision = tp / pred_apply if pred_apply else None
        apply_recall = tp / len(rel_set) if rel_set else None

        return MetricsReport(
            n_jobs=len(self.dataset.jobs),
            hard_constraint_accuracy=round(hard_acc, 4),
            fit_classification_accuracy=round(fit_acc, 4),
            precision_at_5=round(precision_at_5, 4),
            recall_at_10=round(recall_at_10, 4),
            ranking_quality_ndcg10=round(ndcg, 4),
            evidence_accuracy=round(evidence_acc, 4),
            evidence_coverage=round(evidence_cov, 4),
            hallucination_rate=round(hallucination, 4),
            duplicate_detection_rate=round(duplicate_rate, 4),
            expired_job_detection_rate=round(expired_rate, 4),
            should_apply_precision=round(apply_precision, 4) if apply_precision is not None else None,
            should_apply_recall=round(apply_recall, 4) if apply_recall is not None else None,
        )

    # ---------------------------------------------------------------- bits

    def _duplicate_detection_rate(self) -> float:
        from lhas.job.detectors import DuplicateDetector

        gt_groups = {g for g in (l.duplicate_group for l in self.dataset.labels.values()) if g}
        if not gt_groups:
            return 1.0
        detector = DuplicateDetector(self.dataset.ordered_jobs)
        detected = detector.groups()
        # 检出组中,与 GT 组有重叠的占比(按 GT 组计)
        hit = 0
        for group in sorted(gt_groups):
            member_ids = {jid for jid, l in self.dataset.labels.items() if l.duplicate_group == group}
            detected_members = {jid for ids in detected.values() for jid in ids}
            if member_ids & detected_members:
                hit += 1
        return hit / len(gt_groups)

    def _expired_detection_rate(self, evals: list[EvaluationResult]) -> float:
        from lhas.job.detectors import ExpirationValidator

        validator = ExpirationValidator(as_of=self.dataset.as_of_date)
        gt_expired = {jid for jid, l in self.dataset.labels.items() if l.expiration_status == "EXPIRED"}
        if not gt_expired:
            return 1.0
        detected = {job.job_id for job in self.dataset.ordered_jobs if validator.check(job) == "EXPIRED"}
        return len(gt_expired & detected) / len(gt_expired)

    def _ndcg_at_10(self, ranked: list[MatchPrediction]) -> float:
        def dcg(ordered: list[MatchPrediction]) -> float:
            return sum(
                FIT_GAIN.get(self.dataset.labels[p.job_id].expected_fit, 0.0) / math.log2(i + 2)
                for i, p in enumerate(ordered[:10])
            )

        if not ranked:
            return 0.0
        ideal = sorted(
            ranked,
            key=lambda p: FIT_GAIN.get(self.dataset.labels[p.job_id].expected_fit, 0.0),
            reverse=True,
        )
        idcg = dcg(ideal)
        return dcg(ranked) / idcg if idcg else 0.0


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0
