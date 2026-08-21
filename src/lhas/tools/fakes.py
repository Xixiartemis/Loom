from typing import Any, Callable
from .protocol import Tool, ToolRequest, ToolResult, ToolResultStatus
from lhas.planning.models import CapabilitySpec

class FakeTool:
    def __init__(self, capability: CapabilitySpec, handler: Callable[[ToolRequest], Any] | None = None):
        self.capability = capability
        self.handler = handler
        self.name = f"fake:{capability.name}"

    async def execute(self, request: ToolRequest) -> ToolResult:
        value = self.handler(request) if self.handler else {"capability": request.capability, "arguments": request.arguments}
        if isinstance(value, ToolResult): return value
        return ToolResult(status=ToolResultStatus.SUCCESS, output=value, metadata={"fake": True})
