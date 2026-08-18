"""JobBenchRunner — 固定数据集上跑 predictor → evaluator → metrics 的闭环。

Phase C2:rule predictor(不依赖 LLM)立即产出全部指标。
Phase C3:predictor="llm" 时通过 GeneralAgentExecutor 走同一套评估。

一次运行 = 一个实验,必须绑定 git commit 并写入实验记录。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from lhas.job.evaluator import EvaluationResult, GroundTruthEvaluator
from lhas.job.matching import RuleBasedMatcher
from lhas.job.metrics import MetricsCalculator, MetricsReport
from lhas.job.models import JobDataset, MatchPrediction


@dataclass
class JobBenchResult:
    dataset: JobDataset
    predictor: str
    model: Optional[str]
    predictions: list[MatchPrediction]
    evaluations: list[EvaluationResult]
    metrics: MetricsReport


def run_job_bench(
    dataset: JobDataset,
    *,
    predictor: str = "rule",
    predict_fn: Optional[callable] = None,  # noqa: A003 — injected predictor
    as_of: Optional[date] = None,
) -> JobBenchResult:
    """执行一轮 Job Benchmark。

    predictor:
      - "rule": RuleBasedMatcher(确定性,不调模型)
      - "llm":  GeneralAgentExecutor(需 provider 配置;见 executors/general.py)
      - 自定义:传 predict_fn(job) -> MatchPrediction 列表生成器
    """
    if predict_fn is not None:
        predictions = [predict_fn(job) for job in dataset.ordered_jobs]
        model = "custom"
    elif predictor == "rule":
        matcher = RuleBasedMatcher(dataset.profile, dataset.goal)
        predictions = [matcher.predict(job) for job in dataset.ordered_jobs]
        model = None
    elif predictor == "llm":
        from lhas.executors.general import make_llm_predictor

        predictions = [make_llm_predictor(dataset)(job) for job in dataset.ordered_jobs]
        model = "llm"
    else:
        raise ValueError(f"unknown predictor: {predictor}")

    evaluator = GroundTruthEvaluator(dataset)
    evaluations = [evaluator.evaluate(p) for p in sorted(predictions, key=lambda p: p.job_id)]
    metrics = MetricsCalculator(dataset).compute(predictions)
    return JobBenchResult(
        dataset=dataset, predictor=predictor, model=model,
        predictions=predictions, evaluations=evaluations, metrics=metrics,
    )
