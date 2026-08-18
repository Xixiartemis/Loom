"""Metrics 与 Evaluator 测试(docs/09):完美预测 → 全 1.0;坏预测 → 诚实低分。"""

from pathlib import Path

import pytest

from lhas.job.evaluator import GroundTruthEvaluator
from lhas.job.matching import RuleBasedMatcher
from lhas.job.metrics import MetricsCalculator
from lhas.job.models import MatchPrediction, load_job_dataset

DATASET = Path(__file__).resolve().parents[1] / "benchmarks" / "job-v0.1"


@pytest.fixture(scope="module")
def ds():
    return load_job_dataset(DATASET)


def _perfect_predictions(ds) -> list[MatchPrediction]:
    """直接从 GT 构造完美预测(分数按 fit 排序设计)。"""
    score = {"HIGH": 95.0, "MEDIUM": 70.0, "LOW": 30.0}
    out = []
    for jid, gt in ds.labels.items():
        out.append(MatchPrediction(
            job_id=jid, fit=gt.expected_fit, score=score[gt.expected_fit],
            evidence=list(gt.positive_evidence), risks=list(gt.risks),
            hard_constraints_pass=gt.hard_constraints_pass,
            should_apply=gt.should_apply, source="perfect",
        ))
    return out


def test_perfect_predictions_score_1_0(ds):
    metrics = MetricsCalculator(ds).compute(_perfect_predictions(ds))
    assert metrics.hard_constraint_accuracy == 1.0
    assert metrics.fit_classification_accuracy == 1.0
    assert metrics.precision_at_5 == 1.0
    # 相关岗位 = GT should_apply = 20 个(HIGH10 + MEDIUM10),recall@10 上限 0.5
    assert metrics.recall_at_10 == pytest.approx(0.5)
    assert metrics.ranking_quality_ndcg10 == 1.0
    assert metrics.evidence_accuracy == 1.0
    assert metrics.hallucination_rate == 0.0
    assert metrics.duplicate_detection_rate == 1.0
    assert metrics.expired_job_detection_rate == 1.0


def test_rule_predictor_metrics_are_honest(ds):
    matcher = RuleBasedMatcher(ds.profile, ds.goal)
    predictions = [matcher.predict(j) for j in ds.ordered_jobs]
    metrics = MetricsCalculator(ds).compute(predictions)
    # 规则 matcher 与 GT 一致(见 test_job_matching),指标应接近 1.0
    assert metrics.fit_classification_accuracy == 1.0
    assert metrics.hard_constraint_accuracy == 1.0
    assert metrics.hallucination_rate == 0.0


def test_wrong_predictions_are_penalized(ds):
    flipped = []
    for jid, gt in ds.labels.items():
        fit = {"HIGH": "LOW", "MEDIUM": "HIGH", "LOW": "MEDIUM"}[gt.expected_fit]
        flipped.append(MatchPrediction(
            job_id=jid, fit=fit, score=50.0,
            evidence=["编造的事实:候选人精通量子计算"],  # 无依据证据
            risks=[],
            hard_constraints_pass=not gt.hard_constraints_pass,
            should_apply=not gt.should_apply, source="adversarial",
        ))
    metrics = MetricsCalculator(ds).compute(flipped)
    assert metrics.fit_classification_accuracy == 0.0
    assert metrics.hard_constraint_accuracy == 0.0
    assert metrics.evidence_accuracy == 0.0
    assert metrics.hallucination_rate == 1.0


def test_evaluator_detects_hallucination(ds):
    evaluator = GroundTruthEvaluator(ds)
    pred = MatchPrediction(
        job_id="JD-001", fit="HIGH", score=90.0,
        evidence=["React/TypeScript 前端开发", "候选人会驾驶宇宙飞船"],  # 第二条无依据
        risks=[], hard_constraints_pass=True, should_apply=True, source="test",
    )
    result = evaluator.evaluate(pred)
    assert result.hallucination is True
    assert result.grounded_ratio == 0.5
    assert result.evidence_hit == 0.5


def test_missing_predictions_raise(ds):
    with pytest.raises(ValueError):
        MetricsCalculator(ds).compute([])
