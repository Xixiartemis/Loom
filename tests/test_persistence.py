"""Persistence contract tests: entities survive a fresh connection (docs/07)."""

from lhas.domain.enums import AttemptStatus, EventType, RunStatus, TaskStatus
from lhas.domain.models import Attempt, Event, Project, Run, Task
from lhas.persistence.database import Database
from lhas.persistence.event_store import EventStore
from lhas.persistence.repositories import AttemptRepository, ProjectRepository, RunRepository, TaskRepository


def test_project_task_run_attempt_roundtrip_across_connections(db, tmp_path):
    db_path = tmp_path / "reopen.db"

    # --- write with one connection
    db1 = Database(db_path)
    db1.init_db()
    project = ProjectRepository(db1).create(Project(name="p1", type="benchmark"))
    task = TaskRepository(db1).create(
        Task(project_id=project.id, title="t1", objective="o1",
             constraints=["c1"], acceptance_criteria=["a1"],
             max_attempts=3, timeout_seconds=7.5)
    )
    run = RunRepository(db1).create(Run(task_id=task.id, status=RunStatus.RUNNING))
    attempt = AttemptRepository(db1).create(
        Attempt(run_id=run.id, attempt_number=1, status=AttemptStatus.COMPLETED,
                output="hello", duration_ms=12, usage={"tokens": 5})
    )
    EventStore(db1).append(EventType.TASK_CREATED, task_id=task.id, payload={"title": "t1"})
    db1.close()

    # --- read with a fresh connection
    db2 = Database(db_path)
    db2.init_db()
    got_project = ProjectRepository(db2).get_by_name("p1")
    assert got_project is not None and got_project.type == "benchmark"

    got_task = TaskRepository(db2).get(task.id)
    assert got_task is not None
    assert got_task.objective == "o1"
    assert got_task.constraints == ["c1"]
    assert got_task.acceptance_criteria == ["a1"]
    assert got_task.max_attempts == 3
    assert got_task.timeout_seconds == 7.5

    got_run = RunRepository(db2).get(run.id)
    assert got_run is not None
    assert got_run.status is RunStatus.RUNNING
    assert got_run.task_id == task.id

    got_attempt = AttemptRepository(db2).get(attempt.id)
    assert got_attempt is not None
    assert got_attempt.status is AttemptStatus.COMPLETED
    assert got_attempt.output == "hello"
    assert got_attempt.duration_ms == 12
    assert got_attempt.usage == {"tokens": 5}

    got_events = EventStore(db2).list_for_task(task.id)
    assert len(got_events) == 1
    assert got_events[0].event_type is EventType.TASK_CREATED
    assert got_events[0].payload == {"title": "t1"}
    db2.close()


def test_task_update_persists(db):
    repo = TaskRepository(db)
    task = repo.create(Task(project_id="p", title="t", objective="o", status=TaskStatus.RUNNING))
    task.status = TaskStatus.COMPLETED
    repo.update(task)
    assert repo.get(task.id).status is TaskStatus.COMPLETED
    assert TaskStatus(repo.get(task.id).status) is TaskStatus.COMPLETED
