"""JobBenchRunner — 固定数据集上跑 predictor → evaluator → metrics 的闭环。

Phase C2:rule predictor(不依赖 LLM)立即产出全部指标。
Phase C3:predictor="llm" 时通过 GeneralAgentExecutor 走同一套评估。

一次运行 = 一个实验,必须绑定 git commit 并写入实验记录。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional
import asyncio
import json

from lhas.job.evaluator import EvaluationResult, GroundTruthEvaluator
from lhas.job.matching import RuleBasedMatcher
from lhas.job.metrics import MetricsCalculator, MetricsReport
from lhas.job.models import JobDataset, MatchPrediction
from lhas.context_builder import ContextBuilder
from lhas.failure import RuleFailureClassifier
from lhas.job.validation import JobMatchValidator
from lhas.orchestrator_v2 import RecoveringOrchestrator
from lhas.persistence.database import Database
from lhas.persistence.repositories import AttemptRepository, ProjectRepository
from lhas.domain.models import Project
from lhas.recovery import DefaultRecoveryPolicy
from lhas.task_service import create_task


@dataclass
class JobBenchResult:
    dataset: JobDataset
    predictor: str
    model: Optional[str]
    predictions: list[MatchPrediction]
    evaluations: list[EvaluationResult]
    metrics: MetricsReport
    runs: list = field(default_factory=list)


def run_job_bench(
    dataset: JobDataset,
    *,
    predictor: str = "rule",
    predict_fn: Optional[callable] = None,  # noqa: A003 — injected predictor
    as_of: Optional[date] = None,
    runtime: bool = False,
    db: Optional[Database] = None,
) -> JobBenchResult:
    """执行一轮 Job Benchmark。

    predictor:
      - "rule": RuleBasedMatcher(确定性,不调模型)
      - "llm":  GeneralAgentExecutor(需 provider 配置;见 executors/general.py)
      - 自定义:传 predict_fn(job) -> MatchPrediction 列表生成器
    """
    if runtime:
        if predictor != "llm":
            raise ValueError("runtime=True currently requires predictor='llm'")
        if db is None:
            raise ValueError("runtime=True requires a Database so Task/Run/Attempt artifacts can be persisted")
        predictions, runs = _run_job_runtime(dataset, db=db, as_of=as_of)
        predictor = "llm-runtime"
        model = "llm"
    elif predict_fn is not None:
        predictions = [predict_fn(job) for job in dataset.ordered_jobs]
        model = "custom"
        runs = []
    elif predictor == "rule":
        matcher = RuleBasedMatcher(dataset.profile, dataset.goal)
        predictions = [matcher.predict(job) for job in dataset.ordered_jobs]
        model = None
        runs = []
    elif predictor == "llm":
        from lhas.executors.general import make_llm_predictor

        # Construct the client/executor once per benchmark, not once per JD.
        predict = make_llm_predictor(dataset)
        predictions = [predict(job) for job in dataset.ordered_jobs]
        model = "llm"
        runs = []
    else:
        raise ValueError(f"unknown predictor: {predictor}")

    evaluator = GroundTruthEvaluator(dataset)
    evaluations = [evaluator.evaluate(p) for p in sorted(predictions, key=lambda p: p.job_id)]
    metrics = MetricsCalculator(dataset).compute(predictions)
    return JobBenchResult(
        dataset=dataset, predictor=predictor, model=model,
        predictions=predictions, evaluations=evaluations, metrics=metrics,
        runs=runs,
    )


class _JobRuntimeOrchestrator(RecoveringOrchestrator):
    def __init__(self, *args, jobs_by_task: dict[str, dict], **kwargs):
        self._jobs_by_task = jobs_by_task
        super().__init__(*args, **kwargs)

    def _executor_task_payload(self, task):
        payload = super()._executor_task_payload(task)
        payload["job"] = self._jobs_by_task[task.id]
        return payload


def _run_job_runtime(dataset: JobDataset, *, db: Database, as_of: Optional[date] = None):
    """Run each JD through Task→Attempt→Validator→Recovery.

    This is the harness path for Recovery experiments.  Baseline ``run_job_bench``
    remains a direct predictor by design; callers must opt into ``runtime=True``
    for a real Loom Runtime run.
    """
    db.init_db()
    project_repo = ProjectRepository(db)
    project = project_repo.get_by_name("JOB-BENCHMARK")
    if project is None:
        project = project_repo.create(Project(name="JOB-BENCHMARK", type="benchmark"))
    jobs_by_task: dict[str, dict] = {}
    task_ids: list[str] = []
    for job in dataset.ordered_jobs:
        task = create_task(
            db, project_id=project.id, title=job.job_id,
            objective=f"Match {job.job_id}",
            acceptance_criteria=["valid MatchPrediction"], max_attempts=3,
        )
        jobs_by_task[task.id] = job.model_dump(mode="json")
        task_ids.append(task.id)

    from lhas.executors.general import GeneralAgentExecutor, LLMClient, llm_config_from_env
    cfg = llm_config_from_env()
    client = LLMClient(**cfg)  # one provider client for the whole benchmark
    profile = dataset.profile.model_dump(mode="json")
    goal = dataset.goal.model_dump(mode="json")
    context_builder = ContextBuilder(
        policy="CP-2", profile={"candidate_profile": profile, "career_goal": goal}
    )
    orchestrator = _JobRuntimeOrchestrator(
        db,
        jobs_by_task=jobs_by_task,
        executor_factory=lambda: GeneralAgentExecutor(client=client),
        validator=JobMatchValidator(dataset, as_of=as_of),
        classifier=RuleFailureClassifier(),
        recovery_policy=DefaultRecoveryPolicy(context_policy="CP-2"),
        context_builder=context_builder,
        context_policy_version="CP-2",
        executor_type="GeneralAgentExecutor",
        provider="llm",
        model=cfg["model"],
        dataset_version=str(dataset.manifest.get("dataset_id", "JOB-V0.1")),
    )
    runs = []
    predictions: list[MatchPrediction] = []
    for task_id in task_ids:
        run = asyncio.run(orchestrator.execute_task(task_id))
        runs.append(run)
        attempts = AttemptRepository(db).list_for_run(run.id)
        if not attempts or not attempts[-1].output:
            raise RuntimeError(f"runtime produced no prediction for task {task_id}")
        predictions.append(MatchPrediction(**json.loads(attempts[-1].output)))
    return predictions, runs
