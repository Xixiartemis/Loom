"""Job 实验记录器 — EXP-YYYYMMDD-JOB-NNN(docs/10, docs/12)。

结构与 RUNTIME 实验一致:experiment.json(全量元数据 + 指标)、summary.md、
results/(predictions.json + evaluation.json)。只新增、不覆盖。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from lhas.experiments import git_head_info, next_experiment_id
from lhas.job.metrics import MetricsReport


class JobExperimentRecorder:
    def __init__(self, base_dir: str | Path = "experiments"):
        self.base_dir = Path(base_dir)

    def record(
        self,
        *,
        experiment_id: str,
        dataset_id: str,
        ground_truth_status: str,
        predictor: str,
        model: Optional[str],
        provider: Optional[str],
        harness_version: str,
        context_policy_version: str,
        recovery: str,
        metrics: MetricsReport,
        predictions: list[dict[str, Any]],
        evaluations: list[dict[str, Any]],
        git: Optional[dict[str, Any]] = None,
    ) -> Path:
        exp_dir = self.base_dir / experiment_id
        if exp_dir.exists():
            raise FileExistsError(f"experiment already exists: {exp_dir} — never overwrite")
        (exp_dir / "results").mkdir(parents=True)

        git = git or git_head_info()
        metadata = {
            "experiment_id": experiment_id,
            "kind": "JOB_BENCHMARK",
            "timestamp": _now_iso(),
            "git_commit": git["commit"],
            "branch": git["branch"],
            "dirty_workspace": git["dirty_workspace"],
            "dataset_id": dataset_id,
            "ground_truth_status": ground_truth_status,
            "predictor": predictor,
            "model": model,
            "provider": provider,
            "harness_version": harness_version,
            "context_policy_version": context_policy_version,
            "recovery": recovery,
            "metrics": metrics.model_dump(),
        }
        (exp_dir / "experiment.json").write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        (exp_dir / "results" / "predictions.json").write_text(
            json.dumps(predictions, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        (exp_dir / "results" / "evaluation.json").write_text(
            json.dumps(evaluations, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        (exp_dir / "summary.md").write_text(_render_summary(experiment_id, git, metadata), encoding="utf-8")
        return exp_dir

    def next_id(self, area: str = "JOB") -> str:
        return next_experiment_id(self.base_dir, area)


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _render_summary(experiment_id: str, git: dict[str, Any], metadata: dict[str, Any]) -> str:
    m = metadata["metrics"]
    lines = [
        f"# {experiment_id}",
        "",
        f"git_commit: {git['commit']}",
        f"branch: {git['branch']}",
        f"dirty_workspace: {git['dirty_workspace']}",
        f"dataset: {metadata['dataset_id']}",
        f"ground_truth_status: {metadata['ground_truth_status']}",
        f"predictor: {metadata['predictor']}",
        f"model: {metadata['model'] or '-'}",
        f"harness_version: {metadata['harness_version']}",
        f"context_policy: {metadata['context_policy_version']}",
        f"recovery: {metadata['recovery']}",
        "",
        "metrics:",
        f"  hard_constraint_accuracy     {m['hard_constraint_accuracy']:.3f}",
        f"  fit_classification_accuracy  {m['fit_classification_accuracy']:.3f}",
        f"  precision@5                  {m['precision_at_5']:.3f}",
        f"  recall@10                    {m['recall_at_10']:.3f}",
        f"  ranking_quality(ndcg@10)     {m['ranking_quality_ndcg10']:.3f}",
        f"  evidence_accuracy            {m['evidence_accuracy']:.3f}",
        f"  hallucination_rate           {m['hallucination_rate']:.3f}",
        f"  duplicate_detection_rate     {m['duplicate_detection_rate']:.3f}",
        f"  expired_job_detection_rate   {m['expired_job_detection_rate']:.3f}",
        "",
        f"n_jobs: {m['n_jobs']}",
        "",
        "purpose: baseline B0 — deterministic rule predictor, no model involved.",
    ]
    return "\n".join(lines) + "\n"
