"""Dynamic tool registry — the only source of truth is the Studio MCP server itself.

Nothing here hardcodes Roblox tools. If Roblox adds, renames or removes a tool, the
registry follows automatically after a refresh.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .mcp_client import ToolInfo
from .security import classify_tool_level


@dataclass
class Registry:
    tools: dict[str, ToolInfo] = field(default_factory=dict)
    levels: dict[str, int] = field(default_factory=dict)
    version: int = 0
    updated_at: str = ""

    def refresh(self, tools: list[ToolInfo], now: str = "") -> None:
        self.tools = {tool.name: tool for tool in tools if tool.name}
        self.levels = {name: classify_tool_level(name, info.description)
                       for name, info in self.tools.items()}
        self.version += 1
        self.updated_at = now

    def __len__(self) -> int:
        return len(self.tools)

    def get(self, name: str) -> ToolInfo | None:
        return self.tools.get(name)

    def level_of(self, name: str) -> int:
        return self.levels.get(name, 4)

    def schema_of(self, name: str) -> dict[str, Any] | None:
        info = self.tools.get(name)
        return info.schema if info else None

    def names(self) -> list[str]:
        return sorted(self.tools)

    def manifest(self) -> list[dict[str, Any]]:
        return [{"name": name,
                 "description": info.description,
                 "level": self.levels.get(name, 4),
                 "inputSchema": info.schema}
                for name, info in sorted(self.tools.items())]

    def prompt_block(self) -> str:
        """Compact description injected into the AI prompt (name + args, nothing invented)."""
        lines = []
        for name, info in sorted(self.tools.items()):
            props = (info.schema or {}).get("properties") or {}
            required = set((info.schema or {}).get("required") or [])
            args = ", ".join(f"{key}{'' if key in required else '?'}" for key in props)
            desc = (info.description or "").strip().splitlines()[0][:110] if info.description else ""
            lines.append(f"- {name}({args})" + (f" — {desc}" if desc else ""))
        return "\n".join(lines)
