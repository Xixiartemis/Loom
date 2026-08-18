"""Stage B — Phase B acceptance suite (docs/14 Phase B gate).

Runs the Validation + Failure + Recovery pipeline end-to-end:

- recoverable-context:  executor fails attempt 1 with MISSING_CONTEXT ->
                        classified CONTEXT/MISSING_CONTEXT -> recovery policy
                        supplies missing context -> attempt 2 succeeds and
                        passes validation -> TASK_COMPLETED
- validation-feedback:  executor "succeeds" on attempt 1 but the output fails
                        rule validation -> VALIDATION_FAILED -> classified ->
                        recovery carries validation feedback -> attempt 2
                        output passes -> TASK_COMPLETED
- unrecoverable:        executor always fails -> 3 failure reports, recovery
                        actions logged (2 retries + 1 ESCALATE) -> ESCALATED

Phase B gate (docs/14): real FailureReport, RecoveryAction fully logged,
second attempt executed automatically.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from lhas.context_builder import ContextBuilder
from lhas.domain.enums import EventType, RunStatus, TaskStatus
from lhas.domain.models import Attempt, Run, Task
from lhas.executors.mock import MockConfig, MockExecutor, MockScenario
from lhas.experiments import ExperimentRecorder, TaskResult, next_experiment_id
from lhas.failure import RuleFailureClassifier
from lhas.orchestrator_v2 import RecoveringOrchestrator
from lhas.persistence.database import Database
from lhas.persistence.event_store import EventStore
from lhas.persistence.phaseb_repos import (
    ContextSnapshotRepository,
    FailureReportRepository,
    RecoveryActionRepository,
    ValidationResultRepository,
)
from lhas.persistence.repositories import AttemptRepository, TaskRepository
from lhas.recovery import DefaultRecoveryPolicy
from lhas.task_service import create_task
from lhas.validation import RuleValidator


@dataclass
class StageBScenario:
    title: str
    scenario: MockScenario
    expected_markers: list[str] = field(default_factory=list)
    verify: Optional[Callable[[list[str], Task, Run, list[Attempt], Database], tuple[bool, str]]] = None


def _chain(db: Database, task_id: str) -> list[str]:
    return [e.event_type.value for e in EventStore(db).list_for_task(task_id)]


def _verify_recoverable_context(chain, task, run, attempts, db) -> tuple[bool, str]:
    ok = (
        task.status == TaskStatus.COMPLETED
        and len(attempts) == 2
        and chain.count("EXECUTOR_FAILED") == 1
        and chain.count("FAILURE_CLASSIFIED") == 1
        and chain.count("RECOVERY_DECIDED") == 1
        and chain.count("RECOVERY_STARTED") == 1
        and chain.count("VALIDATION_PASSED") == 1
        and chain[-1] == "TASK_COMPLETED"
    )
    if not ok:
        return False, f"chain={chain}"
    # failure report: MISSING_CONTEXT
    report = FailureReportRepository(db).list_for_attempt(attempts[0].id)[0]
    if report.failure_type.value != "MISSING_CONTEXT":
        return False, f"failure_type={report.failure_type.value}"
    # recovery action supplies missing context
    action = RecoveryActionRepository(db).list_for_attempt(attempts[0].id)[0]
    if "missing_context" not in action.added_context:
        return False, f"added_context={action.added_context}"
    # attempt 2 context carries the recovery guidance the mock needs
    snapshots = ContextSnapshotRepository(db).list_for_attempt(attempts[1].id)
    guidance = snapshots[0].sections.get("recovery_guidance", "")
    if "MISSING_CONTEXT" not in guidance:
        return False, "recovery_guidance missing from attempt-2 context"
    if attempts[1].output != "mock-output-recovered":
        return False, f"attempt2 output={attempts[1].output!r}"
    return True, "FAIL→CLASSIFY(MISSING_CONTEXT)→RECOVER→PASS"


def _verify_validation_feedback(chain, task, run, attempts, db) -> tuple[bool, str]:
    ok = (
        task.status == TaskStatus.COMPLETED
        and len(attempts) == 2
        and chain.count("VALIDATION_STARTED") == 2
        and chain.count("VALIDATION_FAILED") == 1
        and chain.count("VALIDATION_PASSED") == 1
        and chain.count("FAILURE_CLASSIFIED") == 1
        and chain.count("RECOVERY_STARTED") == 1
        and chain[-1] == "TASK_COMPLETED"
    )
    if not ok:
        return False, f"chain={chain}"
    v1 = ValidationResultRepository(db).list_for_attempt(attempts[0].id)
    if not (len(v1) == 1 and v1[0].passed is False):
        return False, f"attempt1 validation={[v.passed for v in v1]}"
    v2 = ValidationResultRepository(db).list_for_attempt(attempts[1].id)
    if not (len(v2) == 1 and v2[0].passed is True):
        return False, f"attempt2 validation={[v.passed for v in v2]}"
    if attempts[1].output != "expected:ok":
        return False, f"attempt2 output={attempts[1].output!r}"
    return True, "VALIDATION_FAILED→CLASSIFY→RECOVER→VALIDATION_PASSED"


def _verify_unrecoverable(chain, task, run, attempts, db) -> tuple[bool, str]:
    ok = (
        task.status == TaskStatus.ESCALATED
        and run.status == RunStatus.ESCALATED
        and len(attempts) == 3
        and chain.count("FAILURE_CLASSIFIED") == 3
        and chain.count("RECOVERY_DECIDED") == 3
        and chain.count("RECOVERY_STARTED") == 2
        and chain[-1] == "TASK_ESCALATED"
    )
    if not ok:
        return False, f"chain={chain}"
    # 3 failure reports, 3 recovery actions with the documented escalation ladder
    reports = [FailureReportRepository(db).list_for_attempt(a.id) for a in attempts]
    if any(len(r) != 1 for r in reports):
        return False, "failure report missing for an attempt"
    actions = [RecoveryActionRepository(db).list_for_attempt(a.id)[0] for a in attempts]
    action_types = [a.action_type.value for a in actions]
    expected = ["RETRY_WITH_FAILURE_CONTEXT", "RETRY_WITH_EXPANDED_CONTEXT", "ESCALATE"]
    if action_types != expected:
        return False, f"action ladder={action_types}"
    return True, "3 failures → 3 reports → RETRY/RETRY/ESCALATE"


SCENARIOS: list[StageBScenario] = [
    StageBScenario("recoverable-context", MockScenario.RECOVERABLE, verify=_verify_recoverable_context),
    StageBScenario("validation-feedback", MockScenario.BAD_FIRST_OUTPUT, expected_markers=["expected:ok"], verify=_verify_validation_feedback),
    StageBScenario("unrecoverable", MockScenario.FAIL_ALWAYS, verify=_verify_unrecoverable),
]


def run_stageb(
    db: Database,
    *,
    project_id: str,
    experiments_base: str | Path = "experiments",
    harness_version: str = "HV-0.2",
    dataset_version: str = "RUNTIME-V0.1",
    context_policy_version: str = "CP-2",
    executor_type: str = "MockExecutor",
    provider: str = "mock",
    model: str = "mock-v0",
    experiment_id: Optional[str] = None,
) -> tuple[list[TaskResult], str]:
    results: list[TaskResult] = []
    for spec in SCENARIOS:
        task = create_task(
            db,
            project_id=project_id,
            title=spec.title,
            objective=f"Stage B scenario: {spec.title} (validation + recovery pipeline)",
            max_attempts=3,
            timeout_seconds=10.0,
        )
        orchestrator = RecoveringOrchestrator(
            db,
            executor_factory=lambda s=spec: MockExecutor(MockConfig(scenario=s.scenario)),
            validator=RuleValidator(expected_markers=spec.expected_markers),
            classifier=RuleFailureClassifier(),
            recovery_policy=DefaultRecoveryPolicy(context_policy=context_policy_version),
            context_builder=ContextBuilder(policy=context_policy_version),
            executor_type=executor_type,
            provider=provider,
            model=model,
            harness_version=harness_version,
            context_policy_version=context_policy_version,
            dataset_version=dataset_version,
            experiment_id=experiment_id,
        )
        run = asyncio.run(orchestrator.execute_task(task.id))
        task = TaskRepository(db).get(task.id)
        attempts = AttemptRepository(db).list_for_run(run.id)
        chain = _chain(db, task.id)
        ok, msg = spec.verify(chain, task, run, attempts, db)
        results.append(TaskResult(task, run, attempts, expected=f"{spec.title} (Phase B gate)", passed=ok, notes=msg))

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
        timeout_seconds=10.0,
        max_attempts=3,
    )
    return results, exp_id


def print_stageb(results: list[TaskResult], experiment_id: str) -> int:
    print("=" * 64)
    print("Stage B — Validation / Failure / Recovery acceptance suite")
    print(f"experiment: {experiment_id}")
    print("=" * 64)
    all_pass = True
    for tr in results:
        mark = "PASS" if tr.passed else "FAIL"
        all_pass = all_pass and tr.passed
        print(f"{mark:4s}  {tr.title:<24} task={tr.task.status.value:<10} attempts={len(tr.attempts)}")
        if not tr.passed:
            print(f"       {tr.notes}")
    print("-" * 64)
    print("closed loop verified: FAIL -> CLASSIFY -> RECOVER -> PASS")
    return 0 if all_pass else 1
