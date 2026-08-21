"""Provider-neutral Tool contract."""

from __future__ import annotations

from enum import Enum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from lhas.planning.models import CapabilitySpec


class ToolResultStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    WAITING_FOR_HUMAN_APPROVAL = "WAITING_FOR_HUMAN_APPROVAL"


class ToolRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_call_id: str
    task_id: str
    run_id: str
    attempt_id: str
    capability: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ToolResultStatus
    output: Any = None
    artifacts: dict[str, Any] = Field(default_factory=dict)
    error_type: str | None = None
    error_message: str | None = None
    usage: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Tool(Protocol):
    @property
    def capability(self) -> CapabilitySpec:
        ...

    async def execute(self, request: ToolRequest) -> ToolResult:
        ...
