"""LHAS Typer CLI — minimal entry point (docs/03 tech stack, docs/12)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional

import typer

from lhas import HARNESS_VERSION, DEFAULT_CONTEXT_POLICY_VERSION, DEFAULT_DATASET_VERSION
from lhas.config import db_path, log_dir
from lhas.domain.models import Project, json_loads
from lhas.executors.mock import MockConfig, MockExecutor, MockScenario
from lhas.logging_setup import setup_logging
from lhas.orchestrator import Orchestrator
from lhas.persistence.database import Database
from lhas.persistence.event_store import EventStore
from lhas.persistence.repositories import AttemptRepository, ProjectRepository, RunRepository, TaskRepository
from lhas.stage0 import print_stage0, run_stage0
from lhas.stageb import print_stageb, run_stageb
from lhas.task_service import create_task

app = typer.Typer(help="LHAS — Long-Horizon Agent System runtime / harness CLI.")


def _open_db() -> Database:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    db = Database(path)
    db.init_db()
    return db


@app.command("init-db")
def init_db() -> None:
    """Create the SQLite schema (data/lhas.db)."""
    db = _open_db()
    print(f"database ready: {db_path()}")
    db.close()


@app.command("project-create")
def project_create(
    name: str = typer.Argument(..., help="Project name, e.g. RUNTIME-V0.1"),
    type: str = typer.Option("generic", help="Project type"),
    root_path: Optional[str] = typer.Option(None, help="Project root path"),
) -> None:
    """Create a Project."""
    db = _open_db()
    repo = ProjectRepository(db)
    existing = repo.get_by_name(name)
    if existing:
        print(f"project already exists: {existing.id} ({existing.name})")
    else:
        project = repo.create(Project(name=name, type=type, root_path=root_path))
        print(f"created project: {project.id} ({project.name})")
    db.close()


@app.command("task-create")
def task_create(
    project: str = typer.Option(..., help="Project name"),
    title: str = typer.Argument(..., help="Task title"),
    objective: str = typer.Argument(..., help="Task objective"),
    constraints: Optional[str] = typer.Option(None, help="Comma-separated constraints"),
    acceptance: Optional[str] = typer.Option(None, help="Comma-separated acceptance criteria"),
    max_attempts: int = typer.Option(3, min=1),
    timeout: float = typer.Option(60.0, min=0.1),
) -> None:
    """Create a Task (emits TASK_CREATED)."""
    db = _open_db()
    project_row = ProjectRepository(db).get_by_name(project)
    if project_row is None:
        raise typer.BadParameter(f"project '{project}' not found; run project-create first")
    task = create_task(
        db,
        project_id=project_row.id,
        title=title,
        objective=objective,
        constraints=[c.strip() for c in constraints.split(",")] if constraints else [],
        acceptance_criteria=[c.strip() for c in acceptance.split(",")] if acceptance else [],
        max_attempts=max_attempts,
        timeout_seconds=timeout,
    )
    print(f"created task: {task.id} ({task.title}) status={task.status.value}")
    db.close()


@app.command("task-list")
def task_list(project: Optional[str] = typer.Option(None, help="Filter by project name")) -> None:
    """List tasks."""
    db = _open_db()
    project_repo = ProjectRepository(db)
    project_id = project_repo.get_by_name(project).id if project else None
    for task in TaskRepository(db).list(project_id=project_id):
        print(f"{task.status.value:<10} {task.id}  {task.title}  (attempts<= {task.max_attempts}, timeout={task.timeout_seconds}s)")
    db.close()


@app.command("run")
def run_task(
    task_id: str = typer.Argument(..., help="Task id"),
    scenario: MockScenario = typer.Option(MockScenario.SUCCESS, help="MockExecutor scenario"),
    harness_version: str = typer.Option(HARNESS_VERSION),
) -> None:
    """Run a Task with MockExecutor and print the event chain."""
    db = _open_db()
    task = TaskRepository(db).get(task_id)
    if task is None:
        raise typer.BadParameter(f"task {task_id} not found")
    orchestrator = Orchestrator(
        db,
        executor_factory=lambda: MockExecutor(MockConfig(scenario=scenario)),
        harness_version=harness_version,
    )
    run = asyncio.run(orchestrator.execute_task(task.id))
    attempts = AttemptRepository(db).list_for_run(run.id)
    events = EventStore(db).list_for_task(task.id)
    print(f"task  : {task.title} ({task.id})")
    print(f"run   : {run.id} status={run.status.value}")
    print(f"attempts: {len(attempts)}")
    print("events:")
    for ev in events:
        print(f"  #{ev.id:03d} {ev.event_type.value:<20} attempt={ev.attempt_id or '-'}")
    db.close()


@app.command("events")
def events(
    task_id: str = typer.Argument(..., help="Task id"),
    as_json: bool = typer.Option(False, "--json", help="Emit JSONL"),
) -> None:
    """Show the event timeline for a Task."""
    db = _open_db()
    for ev in EventStore(db).list_for_task(task_id):
        if as_json:
            print(json.dumps({
                "sequence": ev.id, "task_id": ev.task_id, "run_id": ev.run_id,
                "attempt_id": ev.attempt_id, "type": ev.event_type.value,
                "timestamp": ev.timestamp.isoformat(), "payload": ev.payload,
            }, ensure_ascii=False))
        else:
            print(f"#{ev.id:03d} {ev.event_type.value:<22} {ev.timestamp.isoformat()} {json.dumps(ev.payload, ensure_ascii=False)}")
    db.close()


@app.command("stage0")
def stage0() -> None:
    """Run the Phase A Stage 0 acceptance suite and write the experiment record."""
    setup_logging(log_dir())
    db = _open_db()
    project_repo = ProjectRepository(db)
    project = project_repo.get_by_name("RUNTIME-V0.1")
    if project is None:
        project = project_repo.create(Project(name="RUNTIME-V0.1", type="benchmark"))
    results, exp_id = run_stage0(db, project_id=project.id, experiment_id="EXP-20260818-RUNTIME-001")
    exit_code = print_stage0(results, db, exp_id)
    db.close()
    if exit_code != 0:
        raise typer.Exit(code=1)


@app.command("stageb")
def stageb() -> None:
    """Run the Phase B validation/recovery suite and write the experiment record."""
    setup_logging(log_dir())
    db = _open_db()
    project_repo = ProjectRepository(db)
    project = project_repo.get_by_name("RUNTIME-V0.1")
    if project is None:
        project = project_repo.create(Project(name="RUNTIME-V0.1", type="benchmark"))
    results, exp_id = run_stageb(db, project_id=project.id, experiment_id="EXP-20260818-RUNTIME-002")
    exit_code = print_stageb(results, exp_id)
    db.close()
    if exit_code != 0:
        raise typer.Exit(code=1)


@app.command("jobbench")
def jobbench(
    dataset: str = typer.Option("benchmarks/job-v0.1", help="Dataset directory"),
    predictor: str = typer.Option("rule", help="rule (deterministic) | llm (requires LHAS_JOB_LLM_API_KEY)"),
    experiment_id: Optional[str] = typer.Option(None, help="Explicit EXP id (default auto)"),
    as_of: Optional[str] = typer.Option(None, help="Reference date YYYY-MM-DD for expiration"),
    no_record: bool = typer.Option(False, "--no-record", help="Do not write an experiment record"),
) -> None:
    """Run the Job Benchmark on a locked dataset and write an EXP-JOB record."""
    from datetime import date

    from lhas.job.bench import run_job_bench
    from lhas.job.models import labels_status, load_job_dataset
    from lhas.job.recorder import JobExperimentRecorder

    ds = load_job_dataset(dataset)
    print(f"dataset : {ds.manifest.get('dataset_id')} ({len(ds.jobs)} jobs)")
    status = labels_status(ds)
    print(f"labels  : {status}")
    if status.get("DRAFT", 0):
        print("warning : ground truth is DRAFT — metrics are provisional until human review")

    as_of_date = date.fromisoformat(as_of) if as_of else None
    result = run_job_bench(ds, predictor=predictor, as_of=as_of_date)

    m = result.metrics
    print("-" * 56)
    print(f"predictor: {result.predictor}   model: {result.model or '-'}")
    print(f"hard_constraint_accuracy    {m.hard_constraint_accuracy:.3f}")
    print(f"fit_classification_accuracy {m.fit_classification_accuracy:.3f}")
    print(f"precision@5                 {m.precision_at_5:.3f}")
    print(f"recall@10                   {m.recall_at_10:.3f}")
    print(f"ranking_quality (ndcg@10)   {m.ranking_quality_ndcg10:.3f}")
    print(f"evidence_accuracy           {m.evidence_accuracy:.3f}")
    print(f"hallucination_rate          {m.hallucination_rate:.3f}")
    print(f"duplicate_detection_rate    {m.duplicate_detection_rate:.3f}")
    print(f"expired_job_detection_rate  {m.expired_job_detection_rate:.3f}")
    print("-" * 56)
    for e in result.evaluations:
        marks = ("H" if e.hard_correct else "h") + ("F" if e.fit_correct else "f") + ("A" if e.apply_correct else "a")
        print(f"  {e.job_id}  {marks}  hit={e.evidence_hit:.2f} cov={e.evidence_coverage:.2f}{'  HALLUC' if e.hallucination else ''}")

    if no_record:
        return
    recorder = JobExperimentRecorder()
    exp_id = experiment_id or recorder.next_id("JOB")
    recorder.record(
        experiment_id=exp_id,
        dataset_id=ds.manifest.get("dataset_id", "unknown"),
        ground_truth_status=str(status),
        predictor=result.predictor,
        model=result.model,
        provider="mock" if result.predictor == "rule" else "llm",
        harness_version=HARNESS_VERSION,
        context_policy_version="CP-1",
        recovery="OFF",
        metrics=m,
        predictions=[p.model_dump() for p in result.predictions],
        evaluations=[e.model_dump() for e in result.evaluations],
    )
    print(f"experiment record: experiments/{exp_id}/")


@app.command()
def version() -> None:
    """Print version info."""
    print(f"lhas {__import__('lhas').__version__} harness={HARNESS_VERSION}")


if __name__ == "__main__":
    app()
