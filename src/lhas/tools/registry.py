"""Capability-only Tool Registry."""

from __future__ import annotations

from lhas.tools.protocol import Tool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        name = tool.capability.name
        if name in self._tools:
            raise ValueError(f"capability already registered: {name}")
        self._tools[name] = tool

    def resolve(self, capability: str) -> Tool:
        try:
            return self._tools[capability]
        except KeyError as exc:
            raise KeyError(f"unknown capability: {capability}") from exc

    def list_capabilities(self) -> list[str]:
        return sorted(self._tools)

    def specs(self):
        return [self._tools[name].capability for name in self.list_capabilities()]
