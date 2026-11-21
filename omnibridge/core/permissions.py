"""Permission model + tool definitions.

Levels: 1 Read · 2 Assistance (backup+audit) · 3 Controlled automation ·
4 Sensitive (requires confirm=true per call).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from ..config import Config


@dataclass
class ToolDef:
    name: str
    description: str
    params: dict[str, dict[str, Any]] = field(default_factory=dict)
    required: list[str] = field(default_factory=list)
    level: int = 1
    category: str = "misc"
    read_only: bool = True
    handler: Callable[..., Awaitable[Any] | Any] | None = None


class ToolContext:
    def __init__(self, config: Config, db, call_tool, confirmed: bool = False, bridge=None):
        self.config = config
        self.db = db
        self.call_tool = call_tool  # async (name, args, confirmed=False) -> Any
        self.confirmed = confirmed
        self.bridge = bridge  # the OmniBridge container (registry, knowledge, executor…)


class PermissionDenied(Exception):
    pass


_SECRET_PATTERNS = [
    (re.compile(r"(api[_-]?key|token|secret|password|passwd|pwd)\s*[:=]\s*\S+", re.I), r"\1=[REDACTED]"),
    (re.compile(r"\b(gh[pousr]_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16})\b"), "[REDACTED]"),
]


def redact_secrets(text: str) -> str:
    for pat, repl in _SECRET_PATTERNS:
        text = pat.sub(repl, text)
    return text


def check_permission(cfg: Config, tool: ToolDef, args: dict[str, Any]) -> None:
    if tool.level <= cfg.permission_level:
        if tool.level == 4 and args.get("confirm") is not True:
            raise PermissionDenied(
                f'Tool "{tool.name}" is level 4 (sensitive). Pass confirm=true to proceed. '
                "This operation is destructive, external or irreversible."
            )
        return
    raise PermissionDenied(
        f'Tool "{tool.name}" requires permission level {tool.level}, '
        f"but the server is configured for level {cfg.permission_level}. "
        "Raise OMNIBRIDGE_PERMISSION_LEVEL or use a lower-level tool."
    )


def effective_params(tool: "ToolDef") -> dict[str, dict[str, Any]]:
    """Declared parameters, plus `confirm` for level-4 tools so the schema tells the truth."""
    params = dict(tool.params)
    if tool.level >= 4 and "confirm" not in params:
        params["confirm"] = {"type": "boolean", "default": False,
                             "description": "Required: explicitly confirm this sensitive operation."}
    return params
