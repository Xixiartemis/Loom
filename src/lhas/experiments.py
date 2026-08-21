"""Experiment recorder (docs/10_LOGGING_SPEC.md, docs/12_EXPERIMENT_PROTOCOL.md).

Writes one directory per experiment:

    experiments/EXP-YYYYMMDD-<AREA>-<NNN>/
        experiment.json          # full metadata (docs/12)
        summary.md               # human-readable results (user format)
        config/
            executor.json
            harness.json
            environment.json
        tasks/<title>/
            task.json
            result.json
            timeline.jsonl       # event chain for the run
            attempts/attempt-NN/
                context.md
                stdout.log

Historical experiments are never overwritten: a new run gets a new EXP id.
"""

from __future__ import annotations

import json
import platform
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from lhas.domain.enums import EventType
from lhas.domain.models import Attempt, Event, Run, Task, json_loads
from lhas.persistence.database import Database
from lhas.persistence.event_store import EventStore
from lhas.persistence.phaseb_repos import (
    ContextSnapshotRepository,
    FailureReportRepository,
    RecoveryActionRepository,
    ValidationResultRepository,
)
from lhas.persistence.repositories import AttemptRepository, RunRepository, TaskRepository


class TaskResult:
    """Outcome of one scenario task in an experiment."""

    def __init__(
        self,
        task: Task,
        run: Run,
        attempts: list[Attempt],
        expected: str,
        passed: bool,
        notes: str = "",
    ):
        self.task = task
        self.run = run
        self.attempts = attempts
        self.expected = expected
        self.passed = passed
        self.notes = notes

    @property
    def title(self) -> str:
        return self.task.title


def git_head_info() -> dict[str, Any]:
    """Capture the baseline the experiment ran on (docs/03: no Eval w/o commit)."""
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[2],
        ).stdout.strip()
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[2],
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True, text=True, cwd=Path(__file__).resolve().parents[2],
            ).stdout.strip()
        )
    except Exception:  # pragma: no cover
        sha, branch, dirty = "unknown", "unknown", True
    return {"commit": sha, "branch": branch, "dirty_workspace": dirty}


def next_experiment_id(base_dir: Path, area: str = "RUNTIME") -> str:
    """EXP-YYYYMMDD-<AREA>-<NNN> with area sequence = max existing + 1.

    The date is a creation-date prefix, not a sequence namespace; otherwise a
    new day could silently reuse ``-001`` for an existing experiment area.
    """
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    prefix = f"EXP-"
    existing: list[int] = []
    if base_dir.exists():
        for p in base_dir.iterdir():
            m = re.fullmatch(re.escape(prefix) + r"\d{8}-" + re.escape(area) + r"-(\d{3})", p.name)
            if m:
                existing.append(int(m.group(1)))
    n = (max(existing) + 1) if existing else 1
    return f"EXP-{today}-{area}-{n:03d}"


class ExperimentRecorder:
    def __init__(self, db: Database, base_dir: str | Path = "experiments"):
        self.db = db
        self.base_dir = Path(base_dir)
        self._event_store = EventStore(db)
        self._task_repo = TaskRepository(db)
        self._run_repo = RunRepository(db)
        self._attempt_repo = AttemptRepository(db)
        self._snapshot_repo = ContextSnapshotRepository(db)
        self._validation_repo = ValidationResultRepository(db)
        self._failure_repo = FailureReportRepository(db)
        self._action_repo = RecoveryActionRepository(db)

    def record(
        self,
        *,
        experiment_id: str,
        results: list[TaskResult],
        harness_version: str,
        dataset_version: str,
        context_policy_version: str,
        executor: str,
        provider: str,
        model: str,
        timeout_seconds: float,
        max_attempts: int,
        git: Optional[dict[str, Any]] = None,
        allow_dirty: bool = False,
    ) -> Path:
        exp_dir = self.base_dir / experiment_id
        if exp_dir.exists():
            raise FileExistsError(f"Experiment directory already exists: {exp_dir} — historical experiments are never overwritten")
        git = git or git_head_info()
        if git.get("dirty_workspace") and not allow_dirty:
            raise ValueError(
                "formal experiments require a clean git workspace; "
                "pass allow_dirty=True only for development runs"
            )
        (exp_dir / "config").mkdir(parents=True)
        (exp_dir / "tasks").mkdir()
        metadata = {
            "experiment_id": experiment_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "git_commit": git["commit"],
            "branch": git["branch"],
            "dirty_workspace": git["dirty_workspace"],
            "harness_version": harness_version,
            "dataset_version": dataset_version,
            "context_policy_version": context_policy_version,
            "executor": executor,
            "provider": provider,
            "model": model,
            "timeout": timeout_seconds,
            "max_attempts": max_attempts,
            "environment": {
                "python": sys.version.split()[0],
                "platform": platform.platform(),
                "hostname": platform.node(),
            },
        }
        (exp_dir / "experiment.json").write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        (exp_dir / "config" / "executor.json").write_text(
            json.dumps({"executor": executor, "provider": provider, "model": model, "timeout": timeout_seconds, "max_attempts": max_attempts}, indent=2),
            encoding="utf-8",
        )
        (exp_dir / "config" / "harness.json").write_text(
            json.dumps({"harness_version": harness_version, "context_policy_version": context_policy_version, "dataset_version": dataset_version}, indent=2),
            encoding="utf-8",
        )
        (exp_dir / "config" / "environment.json").write_text(
            json.dumps(metadata["environment"], indent=2), encoding="utf-8"
        )

        per_task: dict[str, str] = {}
        for tr in results:
            per_task[tr.title] = "PASS" if tr.passed else "FAIL"
            self._write_task_dir(exp_dir / "tasks" / tr.title, tr)

        summary = self._render_summary(experiment_id, git, metadata, results)
        (exp_dir / "summary.md").write_text(summary, encoding="utf-8")
        return exp_dir

    # ------------------------------------------------------------------ bits

    def _write_task_dir(self, task_dir: Path, tr: TaskResult) -> None:
        task_dir.mkdir(parents=True)
        (task_dir / "task.json").write_text(
            json.dumps(tr.task.model_dump(mode="json"), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        (task_dir / "result.json").write_text(
            json.dumps({
                "run_id": tr.run.id,
                "run_status": tr.run.status.value,
                "task_status": tr.task.status.value,
                "attempt_count": len(tr.attempts),
                "expected": tr.expected,
                "passed": tr.passed,
                "notes": tr.notes,
                "run_result": json_loads(tr.run.result) if tr.run.result else None,
            }, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        events = self._event_store.list_for_task(tr.task.id)
        with (task_dir / "timeline.jsonl").open("w", encoding="utf-8") as fh:
            for ev in events:
                fh.write(json.dumps(self._event_to_dict(ev), ensure_ascii=False) + "\n")

        attempts_dir = task_dir / "attempts"
        attempts_dir.mkdir(exist_ok=True)
        for attempt in tr.attempts:
            a_dir = attempts_dir / f"attempt-{attempt.attempt_number:02d}"
            a_dir.mkdir(exist_ok=True)
            snapshot = (
                self._snapshot_repo.get(attempt.context_snapshot_id)
                if attempt.context_snapshot_id else None
            )
            (a_dir / "context.json").write_text(
                json.dumps(snapshot.model_dump(mode="json") if snapshot else None,
                           indent=2, ensure_ascii=False), encoding="utf-8"
            )
            (a_dir / "context.md").write_text(
                snapshot.raw_text if snapshot else self._render_context(attempt), encoding="utf-8"
            )
            validations = self._validation_repo.list_for_attempt(attempt.id)
            failures = self._failure_repo.list_for_attempt(attempt.id)
            actions = self._action_repo.list_for_attempt(attempt.id)
            (a_dir / "validation.json").write_text(
                json.dumps([v.model_dump(mode="json") for v in validations], indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            (a_dir / "failure.json").write_text(
                json.dumps([f.model_dump(mode="json") for f in failures], indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            (a_dir / "recovery.json").write_text(
                json.dumps([a.model_dump(mode="json") for a in actions], indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            executor_result = json_loads(attempt.executor_result) if attempt.executor_result else None
            (a_dir / "executor-result.json").write_text(
                json.dumps(executor_result, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            (a_dir / "usage.json").write_text(
                json.dumps(attempt.usage, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            (a_dir / "stdout.log").write_text(
                (attempt.output or "") + "\n", encoding="utf-8"
            )
            stderr = ""
            if executor_result:
                stderr = executor_result.get("error_message") or ""
            (a_dir / "stderr.log").write_text(stderr + "\n", encoding="utf-8")

    @staticmethod
    def _event_to_dict(ev: Event) -> dict[str, Any]:
        return {
            "sequence": ev.id,
            "task_id": ev.task_id,
            "run_id": ev.run_id,
            "attempt_id": ev.attempt_id,
            "type": ev.event_type.value,
            "timestamp": ev.timestamp.isoformat(),
            "payload": ev.payload,
        }

    @staticmethod
    def _render_context(attempt: Attempt) -> str:
        head = [
            f"# Attempt {attempt.attempt_number}",
            f"- status: {attempt.status.value}",
            f"- context_snapshot_id: {attempt.context_snapshot_id}",
            f"- error_type: {attempt.error_type}",
            f"- error_message: {attempt.error_message}",
            "",
        ]
        return "\n".join(head)

    @staticmethod
    def _render_summary(experiment_id, git, metadata, results: list[TaskResult]) -> str:
        lines = [
            f"# {experiment_id}",
            "",
            f"git_commit: {git['commit']}",
            f"branch: {git['branch']}",
            f"dirty_workspace: {git['dirty_workspace']}",
            f"harness_version: {metadata['harness_version']}",
            f"dataset: {metadata['dataset_version']}",
            f"context_policy: {metadata['context_policy_version']}",
            f"executor: {metadata['executor']}",
            f"provider: {metadata['provider']}",
            f"model: {metadata['model']}",
            f"tasks: {len(results)}",
            "",
            "results:",
        ]
        for tr in results:
            lines.append(f"{tr.title:<24} {'PASS' if tr.passed else 'FAIL'}")
        lines.append("")
        lines.append("purpose: this record proves the LHAS runtime, state machine,")
        lines.append("logging and experiment infrastructure are reliable under MockExecutor.")
        lines.append("Each subsequent harness change is compared against this baseline.")
        return "\n".join(lines) + "\n"
