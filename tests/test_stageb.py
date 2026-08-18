"""Stage B suite test — Phase B acceptance gate (docs/14)."""

import json

from lhas.stageb import run_stageb


def test_stageb_all_scenarios_pass(db, tmp_path, project):
    results, exp_id = run_stageb(
        db, project_id=project.id, experiments_base=tmp_path / "exps",
        experiment_id="EXP-TEST-RUNTIME-010",
    )
    assert len(results) == 3
    for tr in results:
        assert tr.passed, f"{tr.title}: {tr.notes}"
    assert exp_id == "EXP-TEST-RUNTIME-010"


def test_stageb_experiment_record_metadata(db, tmp_path, project):
    base = tmp_path / "exps"
    results, exp_id = run_stageb(db, project_id=project.id, experiments_base=base, experiment_id="EXP-TEST-RUNTIME-011")
    exp_dir = base / exp_id
    assert exp_dir.exists()
    meta = json.loads((exp_dir / "experiment.json").read_text(encoding="utf-8"))
    assert meta["harness_version"] == "HV-0.2"  # harness version bumped (docs/12)
    assert meta["context_policy_version"] == "CP-2"
    assert meta["executor"] == "MockExecutor"

    summary = (exp_dir / "summary.md").read_text(encoding="utf-8")
    assert "tasks: 3" in summary
    for title in ["recoverable-context", "validation-feedback", "unrecoverable"]:
        assert f"{title:<24} PASS" in summary

    # closed-loop chain recorded in the timeline
    timeline = [json.loads(line) for line in (exp_dir / "tasks" / "recoverable-context" / "timeline.jsonl").read_text(encoding="utf-8").splitlines()]
    types = [e["type"] for e in timeline]
    for required in ["FAILURE_CLASSIFIED", "RECOVERY_DECIDED", "RECOVERY_STARTED", "VALIDATION_PASSED", "TASK_COMPLETED"]:
        assert required in types


def test_stageb_recovery_success_rate(db, tmp_path, project):
    """2 of 3 tasks recover; the unrecoverable one escalates — the pipeline
    must never convert failure into success."""
    results, _ = run_stageb(db, project_id=project.id, experiments_base=tmp_path / "exps", experiment_id="EXP-TEST-RUNTIME-012")
    by_title = {tr.title: tr for tr in results}
    assert by_title["recoverable-context"].task.status.value == "COMPLETED"
    assert by_title["validation-feedback"].task.status.value == "COMPLETED"
    assert by_title["unrecoverable"].task.status.value == "ESCALATED"
    assert len(by_title["unrecoverable"].attempts) == 3
