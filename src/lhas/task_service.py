"""Task creation service — ensures TASK_CREATED is emitted at creation time
(events must come from real state changes; docs/03, docs/10)."""

from __future__ import annotations

from typing import Optional

from lhas.domain.enums import EventType
from lhas.domain.models import Task
from lhas.persistence.database import Database
from lhas.persistence.event_store import EventStore
from lhas.persistence.repositories import TaskRepository


def create_task(
    db: Database,
    *,
    project_id: str,
    title: str,
    objective: str,
    constraints: Optional[list[str]] = None,
    acceptance_criteria: Optional[list[str]] = None,
    max_attempts: int = 3,
    timeout_seconds: float = 60.0,
    emit_event: bool = True,
) -> Task:
    """Create a Task (CREATED) and emit TASK_CREATED."""
    task = Task(
        project_id=project_id,
        title=title,
        objective=objective,
        constraints=constraints or [],
        acceptance_criteria=acceptance_criteria or [],
        max_attempts=max_attempts,
        timeout_seconds=timeout_seconds,
    )
    TaskRepository(db).create(task)
    if emit_event:
        EventStore(db).append(
            EventType.TASK_CREATED,
            task_id=task.id,
            payload={"title": task.title, "objective": task.objective},
        )
    return task
