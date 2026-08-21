"""Stage 0 — Phase A acceptance suite (docs/11_BENCHMARK_TASKS.md, docs/14).

Runs the five MockExecutor scenarios end-to-end against a real SQLite DB,
verifies each against its acceptance criteria, prints the canonical event
chain, and writes the first experiment record.

Scenarios:
- success-path          SUCCESS       -> TASK_COMPLETED, 1 attempt
- fail-once-pass        FAIL_ONCE(1)  -> TASK_COMPLETED, 2 attempts, RETRY path
- timeout               TIMEOUT       -> ESCALATED, ATTEMPT_TIMED_OUT x3
- crash                 CRASH         -> ESCALATED, ATTEMPT_CRASHED x3
- three-fail-escalate   FAIL_ALWAYS   -> ESCALATED, ATTEMPT_FAILED x3, RETRY x2
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from lhas.domain.enums import AttemptStatus, EventType, RunStatus, TaskStatus
from lhas.domain.models import Attempt, Run, Task
from lhas.executors.mock import MockConfig, MockExecutor, MockScenario
from lhas.experiments import ExperimentRecorder, TaskResult, next_experiment_id
from lhas.orchestrator import Orchestrator
from lhas.persistence.database import Database
from lhas.persistence.event_store import EventStore
from lhas.persistence.repositories import AttemptRepository, RunRepository, TaskRepository
from lhas.task_service import create_task

# The canonical Phase A acceptance chain (user spec + docs/14 gate).
FAIL_ONCE_CHAIN = [
    "TASK_CREATED",
    "RUN_STARTED",
    "ATTEMPT_STARTED",
    "EXECUTOR_FAILED",
    "ATTEMPT_FAILED",
    "RETRY_SCHEDULED",
    "ATTEMPT_STARTED",
    "EXECUTOR_COMPLETED",
    "ATTEMPT_COMPLETED",
    "RUN_COMPLETED",
    "TASK_COMPLETED",
]


@dataclass
class ScenarioSpec:
    title: str
    scenario: MockScenario
    timeout_seconds: float
    max_attempts: int = 3
    verify: Callable[[list[str], Task, Run, list[Attempt]], tuple[bool, str]] = field(default=lambda *_: (True, ""))


def _chain(db: Database, task_id: str) -> list[str]:
    return [e.event_type.value for e in EventStore(db).list_for_task(task_id)]


def _has_subsequence(chain: list[str], sub: list[str]) -> bool:
    it = iter(chain)
    return all(x in it for x in sub)


def _verify_default(expect_status: TaskStatus, expect_attempts: int, notes: str = ""):
    def verify(chain: list[str], task: Task, run: Run, attempts: list[Attempt]) -> tuple[bool, str]:
        ok = task.status == expect_status and len(attempts) == expect_attempts
        return ok, f"task={task.status.value} attempts={len(attempts)} {notes}".strip()
    return verify


def _verify_fail_once(chain: list[str], task: Task, run: Run, attempts: list[Attempt]) -> tuple[bool, str]:
    ok = (
        task.status == TaskStatus.COMPLETED
        and len(attempts) == 2
        and _has_subsequence(chain, FAIL_ONCE_CHAIN)
        and chain.count("EXECUTOR_FAILED") == 1
    )
    return ok, "full acceptance chain present, 1 failure then success"


def _verify_timeout(chain: list[str], task: Task, run: Run, attempts: list[Attempt]) -> tuple[bool, str]:
    ok = (
        task.status == TaskStatus.ESCALATED
        and len(attempts) == 3
        and chain.count("ATTEMPT_TIMED_OUT") == 3
    )
    return ok, "3 attempts timed out, escalated"


def _verify_crash(chain: list[str], task: Task, run: Run, attempts: list[Attempt]) -> tuple[bool, str]:
    ok = task.status == TaskStatus.ESCALATED and len(attempts) == 3 and chain.count("ATTEMPT_CRASHED") == 3
    return ok, "3 attempts crashed, escalated"


def _verify_three_fail(chain: list[str], task: Task, run: Run, attempts: list[Attempt]) -> tuple[bool, str]:
    ok = (
        task.status == TaskStatus.ESCALATED
        and len(attempts) == 3
        and chain.count("ATTEMPT_FAILED") == 3
        and chain.count("RETRY_SCHEDULED") == 2
    )
    return ok, "3 failures, escalated after max attempts"


SCENARIOS: list[ScenarioSpec] = [
    ScenarioSpec("success-path", MockScenario.SUCCESS, 5.0, verify=_verify_default(TaskStatus.COMPLETED, 1)),
    ScenarioSpec("fail-once-pass", MockScenario.FAIL_ONCE, 5.0, verify=_verify_fail_once),
    ScenarioSpec("timeout", MockScenario.TIMEOUT, 2.0, verify=_verify_timeout),
    ScenarioSpec("crash", MockScenario.CRASH, 5.0, verify=_verify_crash),
    ScenarioSpec("three-fail-escalate", MockScenario.FAIL_ALWAYS, 5.0, verify=_verify_three_fail),
]


def _event_reasons(db: Database, task_id: str, event_type: EventType) -> list[Any]:
    return [
        e.payload.get("reason")
        for e in EventStore(db).list_for_task(task_id)
        if e.event_type == event_type
    ]


def run_stage0(
    db: Database,
    *,
    project_id: str,
    experiments_base: str | Path = "experiments",
    harness_version: str = "HV-0.1",
    dataset_version: str = "RUNTIME-V0.1",
    context_policy_version: str = "CP-0",
    executor_type: str = "MockExecutor",
    provider: str = "mock",
    model: str = "mock-v0",
    experiment_id: Optional[str] = None,
) -> tuple[list[TaskResult], str]:
    """Run all Stage 0 scenarios, verify, and write the experiment record.

    Returns (results, experiment_id).
    """
    results: list[TaskResult] = []
    for spec in SCENARIOS:
        task = create_task(
            db,
            project_id=project_id,
            title=spec.title,
            objective=f"Stage 0 scenario: {spec.title} (MockExecutor, deterministic)",
            max_attempts=spec.max_attempts,
            timeout_seconds=spec.timeout_seconds,
        )
        orchestrator = Orchestrator(
            db,
            executor_factory=lambda s=spec: MockExecutor(MockConfig(scenario=s.scenario)),
            executor_type=executor_type,
            provider=provider,
            model=model,
            harness_version=harness_version,
            context_policy_version=context_policy_version,
            dataset_version=dataset_version,
            experiment_id=experiment_id,
        )
        run = asyncio.run(orchestrator.execute_task(task.id))
        # Reload the task: the orchestrator persisted its status updates to the
        # DB through its own domain instance — re-read to see the final state.
        task = TaskRepository(db).get(task.id)
        attempts = AttemptRepository(db).list_for_run(run.id)
        chain = _chain(db, task.id)

        # Extra payload-level checks (timeout/crash reasons on EXECUTOR_FAILED).
        notes = ""
        ok, msg = spec.verify(chain, task, run, attempts)
        if spec.title == "timeout":
            reasons = _event_reasons(db, task.id, EventType.EXECUTOR_FAILED)
            ok = ok and reasons == ["timeout"] * 3
            notes = "reason=timeout on every EXECUTOR_FAILED"
        elif spec.title == "crash":
            reasons = _event_reasons(db, task.id, EventType.EXECUTOR_FAILED)
            ok = ok and reasons == ["crash"] * 3
            notes = "reason=crash on every EXECUTOR_FAILED"

        results.append(TaskResult(task, run, attempts, expected=f"{spec.title} -> {spec.verify.__name__}", passed=ok, notes=notes))

    recorder = ExperimentRecorder(db, base_dir=experiments_base)
    exp_id = experiment_id or next_experiment_id(Path(experiments_base), "RUNTIME")
    recorder.record(
        experiment_id=exp_id,
        results=results,
        harness_version=harness_version,
        dataset_version=dataset_version,
        context_policy_version=context_policy_version,
        executor=executor_type,
        provider=provider,
        model=model,
        timeout_seconds=max(s.timeout_seconds for s in SCENARIOS),
        max_attempts=3,
        allow_dirty=True,  # local acceptance suite; formal Eval uses the strict default
    )
    return results, exp_id


def print_stage0(results: list[TaskResult], db: Database, experiment_id: str) -> int:
    print("=" * 64)
    print(f"Stage 0 — Phase A Core Runtime acceptance suite")
    print(f"experiment: {experiment_id}")
    print("=" * 64)
    all_pass = True
    for tr in results:
        mark = "PASS" if tr.passed else "FAIL"
        all_pass = all_pass and tr.passed
        print(f"{mark:4s}  {tr.title:<24} task={tr.task.status.value:<10} attempts={len(tr.attempts)} {tr.notes}")
    print("-" * 64)
    # Canonical chain for fail-once-pass (the Phase A acceptance chain).
    for tr in results:
        if tr.title == "fail-once-pass":
            chain = _chain(db, tr.task.id)
            print("Canonical acceptance chain (fail-once-pass):")
            for name in FAIL_ONCE_CHAIN:
                if name in chain:
                    print(f"  {name}  ✔")
                else:
                    print(f"  {name}  ✘ MISSING")
                    all_pass = False
    print("-" * 64)
    print(f"experiment record: experiments/{experiment_id}/")
    return 0 if all_pass else 1
