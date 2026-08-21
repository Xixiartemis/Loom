"""Phase C hardening: a Job validation failure must traverse the Runtime loop."""

import asyncio
import json
from pathlib import Path

from lhas.domain.enums import EventType, RunStatus
from lhas.executors.protocol import ExecutionResult
from lhas.failure import RuleFailureClassifier
from lhas.job.models import MatchPrediction, load_job_dataset
from lhas.job.validation import JobMatchValidator
from lhas.orchestrator_v2 import RecoveringOrchestrator
from lhas.persistence.event_store import EventStore
from lhas.persistence.phaseb_repos import (
    ContextSnapshotRepository,
    FailureReportRepository,
    ValidationResultRepository,
)
from lhas.recovery import DefaultRecoveryPolicy
from lhas.context_builder import ContextBuilder
from lhas.domain.enums import ExecutionStatus


DATASET = Path(__file__).resolve().parents[1] / "benchmarks" / "job-v0.1"


class FakeJobExecutor:
    name = "FakeJobExecutor"

    async def execute(self, request):
        prediction = MatchPrediction(
            job_id="JD-013",
            fit="HIGH" if request.attempt_number == 1 else "LOW",
            score=90.0 if request.attempt_number == 1 else 30.0,
            evidence=["Python"],
            risks=[],
            hard_constraints_pass=True,
            should_apply=True,
            source="fake",
        )
        return ExecutionResult(
            status=ExecutionStatus.SUCCESS,
            output=json.dumps(prediction.model_dump()),
        )

    async def resume(self, request):
        return await self.execute(request)

    async def cancel(self, run_id):
        return None

    async def status(self, run_id):
        return {"run_id": run_id, "state": "idle"}


def test_job_failure_recovery_runs_through_runtime(make_task, db):
    dataset = load_job_dataset(DATASET)
    task = make_task(title="job-runtime", objective="match JD-013", max_attempts=3)
    orchestrator = RecoveringOrchestrator(
        db,
        executor_factory=FakeJobExecutor,
        validator=JobMatchValidator(dataset),
        classifier=RuleFailureClassifier(),
        recovery_policy=DefaultRecoveryPolicy(context_policy="CP-2"),
        context_builder=ContextBuilder(policy="CP-2"),
        context_policy_version="CP-2",
    )

    run = asyncio.run(orchestrator.execute_task(task.id))

    assert run.status is RunStatus.COMPLETED
    attempts = orchestrator.attempt_repo.list_for_run(run.id)
    assert len(attempts) == 2
    assert attempts[0].context_snapshot_id != attempts[1].context_snapshot_id
    assert FailureReportRepository(db).list_for_attempt(attempts[0].id)[0].failure_type.value == "WRONG_MATCH"
    assert ValidationResultRepository(db).list_for_attempt(attempts[0].id)[0].attempt_id == attempts[0].id
    assert ValidationResultRepository(db).list_for_attempt(attempts[1].id)[0].passed is True
    assert all(s.policy == "CP-2" for a in attempts for s in ContextSnapshotRepository(db).list_for_attempt(a.id))
    event_types = [e.event_type for e in EventStore(db).list_for_task(task.id)]
    assert EventType.FAILURE_CLASSIFIED in event_types
    assert EventType.RECOVERY_STARTED in event_types
    assert EventType.TASK_COMPLETED in event_types
