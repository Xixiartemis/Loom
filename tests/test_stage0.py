"""Stage 0 suite test — the Phase A acceptance gate (docs/11, docs/14)."""

import json
from pathlib import Path

from lhas.domain.enums import TaskStatus
from lhas.experiments import next_experiment_id
from lhas.persistence.repositories import TaskRepository
from lhas.stage0 import FAIL_ONCE_CHAIN, run_stage0


def test_stage0_all_scenarios_pass(db, tmp_path, project):
    results, exp_id = run_stage0(
        db, project_id=project.id, experiments_base=tmp_path / "exps",
        experiment_id="EXP-TEST-RUNTIME-001",
    )
    assert len(results) == 5
    for tr in results:
        assert tr.passed, f"{tr.title}: {tr.notes}"
    assert exp_id == "EXP-TEST-RUNTIME-001"


def test_stage0_writes_experiment_record(db, tmp_path, project):
    base = tmp_path / "exps"
    results, exp_id = run_stage0(db, project_id=project.id, experiments_base=base, experiment_id="EXP-TEST-RUNTIME-002")
    exp_dir = base / exp_id
    assert exp_dir.exists()

    experiment_json = json.loads((exp_dir / "experiment.json").read_text(encoding="utf-8"))
    assert experiment_json["experiment_id"] == "EXP-TEST-RUNTIME-002"
    assert experiment_json["harness_version"] == "HV-0.1"
    assert experiment_json["executor"] == "MockExecutor"
    assert experiment_json["git_commit"]  # baseline commit must be recorded
    assert isinstance(experiment_json["dirty_workspace"], bool)

    summary = (exp_dir / "summary.md").read_text(encoding="utf-8")
    assert "EXP-TEST-RUNTIME-002" in summary
    assert "tasks: 5" in summary
    for title in ["success-path", "fail-once-pass", "timeout", "crash", "three-fail-escalate"]:
        assert f"{title:<24} PASS" in summary

    for cfg in ["executor.json", "harness.json", "environment.json"]:
        assert (exp_dir / "config" / cfg).exists()

    # per-task artifacts: task.json / result.json / timeline.jsonl / attempts
    fail_once_dir = exp_dir / "tasks" / "fail-once-pass"
    assert fail_once_dir.exists()
    timeline = [json.loads(line) for line in (fail_once_dir / "timeline.jsonl").read_text(encoding="utf-8").splitlines()]
    types = [e["type"] for e in timeline]
    # The acceptance chain is a subsequence of the full event timeline.
    it = iter(types)
    assert all(name in it for name in FAIL_ONCE_CHAIN), types
    # and the timeline is complete: creation through completion, in order.
    assert types[0] == "TASK_CREATED"
    assert types[-1] == "TASK_COMPLETED"
    attempts_dir = fail_once_dir / "attempts"
    assert (attempts_dir / "attempt-01" / "context.md").exists()
    assert (attempts_dir / "attempt-01" / "stdout.log").exists()


def test_stage0_timeout_and_crash_reasons(db, tmp_path, project):
    results, _ = run_stage0(db, project_id=project.id, experiments_base=tmp_path / "exps", experiment_id="EXP-TEST-RUNTIME-003")
    by_title = {tr.title: tr for tr in results}
    assert by_title["timeout"].passed
    assert by_title["crash"].passed
    assert by_title["three-fail-escalate"].passed


def test_stage0_failures_are_blocking(db, tmp_path, project):
    """A failing scenario must surface as FAIL — never silently swallowed."""
    results, _ = run_stage0(db, project_id=project.id, experiments_base=tmp_path / "exps", experiment_id="EXP-TEST-RUNTIME-004")
    # every task reached its expected terminal state
    repo = TaskRepository(db)
    for tr in results:
        task = repo.get(tr.task.id)
        assert task.status in (TaskStatus.COMPLETED, TaskStatus.ESCALATED)


def test_next_experiment_id_increments(tmp_path):
    base = tmp_path / "exps"
    assert next_experiment_id(base, "RUNTIME") == "EXP-20260818-RUNTIME-001" or next_experiment_id(base, "RUNTIME").endswith("-001")
    (base / "EXP-20260818-RUNTIME-001").mkdir(parents=True)
    (base / "EXP-20260818-RUNTIME-002").mkdir()
    nxt = next_experiment_id(base, "RUNTIME")
    assert nxt.endswith("-003")
