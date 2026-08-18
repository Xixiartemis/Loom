"""Domain entities (Pydantic) per docs/02_DOMAIN_MODEL.md.

Domain models are pure data + validation. They never import SQLAlchemy.
Persistence mapping lives in lhas/persistence/.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from lhas.domain.enums import AttemptStatus, EventType, RunStatus, TaskStatus


def new_id() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _json_default(o: Any) -> Any:
    if isinstance(o, datetime):
        return o.isoformat()
    if isinstance(o, Enum):
        return o.value
    return str(o)


def json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=_json_default)


def json_loads(raw: Optional[str]) -> Any:
    if raw is None or raw == "":
        return None
    return json.loads(raw)


class Project(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=new_id)
    name: str
    type: str = "generic"
    root_path: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)


class Task(BaseModel):
    """A unit of work: objective + constraints + acceptance criteria."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=new_id)
    project_id: str
    title: str
    objective: str
    constraints: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    status: TaskStatus = TaskStatus.CREATED
    # Execution policy (Phase A extension: drives retry/escalation + timeout).
    max_attempts: int = Field(default=3, ge=1)
    timeout_seconds: float = Field(default=60.0, gt=0)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Run(BaseModel):
    """One execution pass over a Task under a fixed experiment configuration."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=new_id)
    task_id: str
    experiment_id: Optional[str] = None
    executor_type: str = "MockExecutor"
    provider: str = "mock"
    model: str = "mock-v0"
    harness_version: str = "HV-0.1"
    context_policy_version: str = "CP-0"
    dataset_version: str = "RUNTIME-V0.1"
    status: RunStatus = RunStatus.CREATED
    result: Optional[str] = None  # JSON payload of the final result
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utcnow)


class Attempt(BaseModel):
    """One executor invocation inside a Run."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=new_id)
    run_id: str
    attempt_number: int = Field(ge=1)
    status: AttemptStatus = AttemptStatus.PENDING
    context_snapshot_id: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    executor_result: Optional[str] = None  # JSON-serialized ExecutionResult
    usage: dict[str, Any] = Field(default_factory=dict)
    failure_type: Optional[str] = None  # FailureType value (Phase B fills it)
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    output: Optional[str] = None
    duration_ms: Optional[int] = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Event(BaseModel):
    """One state transition. Append-only; sequence == database id."""

    model_config = ConfigDict(extra="forbid")

    id: Optional[int] = None
    task_id: Optional[str] = None
    run_id: Optional[str] = None
    attempt_id: Optional[str] = None
    event_type: EventType
    timestamp: datetime = Field(default_factory=utcnow)
    payload: dict[str, Any] = Field(default_factory=dict)

    @property
    def sequence(self) -> Optional[int]:
        return self.id
