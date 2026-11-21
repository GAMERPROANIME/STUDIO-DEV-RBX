"""Central tool registry: every module registers here; the MCP layer exposes all."""
from __future__ import annotations

from .logger import log
from .permissions import ToolDef


class Registry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDef] = {}

    def register(self, tool: ToolDef) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Duplicate tool: {tool.name}")
        self._tools[tool.name] = tool
        log.debug("tool registered", extra={"tool": tool.name, "category": tool.category, "level": tool.level})

    def get(self, name: str) -> ToolDef | None:
        return self._tools.get(name)

    def list(self) -> list[ToolDef]:
        return sorted(self._tools.values(), key=lambda t: t.name)

    def categories(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for t in self.list():
            out.setdefault(t.category, []).append(t.name)
        return out

    @property
    def size(self) -> int:
        return len(self._tools)
