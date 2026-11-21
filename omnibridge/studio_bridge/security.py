"""Security primitives: pairing token, origin policy, message validation, audit, rate limits.

Threat model: a random website must never be able to drive Roblox Studio.
Therefore:
  • the socket binds 127.0.0.1 only;
  • the HTTP origin must be an extension origin (chrome-extension://…); plain web origins
    are rejected before the upgrade completes;
  • the first frame must be a `hello` carrying the pairing token (constant-time compare);
  • every message is validated against a strict schema and a byte-size limit;
  • every tool call is checked against the discovered tool schema and a permission level;
  • everything is appended to an audit log on disk.
"""
from __future__ import annotations

import json
import re
import secrets
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LEVEL_HINTS: list[tuple[re.Pattern[str], int]] = [
    # destructive / arbitrary code execution first
    (re.compile(r"execute|run_?code|eval|eval_?script|run_?script", re.I), 4),
    # mutations
    (re.compile(r"create|insert|delete|remove|destroy|set_|update|edit|write|rename|move|"
                r"playtest|start_?play|stop_?play|undo|redo|apply", re.I), 3),
    # reads
    (re.compile(r"list|get|read|search|grep|inspect|find|describe|capture|screenshot|state|"
                r"status|tree|history|version|schema", re.I), 1),
]

_SECRET_PATTERNS = [
    (re.compile(r"(api[_-]?key|token|secret|password|passwd|pwd)\s*[:=]\s*\S+", re.I), r"\1=[REDACTED]"),
    (re.compile(r"\b(gh[pousr]_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16})\b"), "[REDACTED]"),
]


def redact(text: str) -> str:
    for pattern, repl in _SECRET_PATTERNS:
        text = pattern.sub(repl, text)
    return text


def classify_tool_level(name: str, description: str = "") -> int:
    """Best-effort permission level from the real tool name/description (never invented)."""
    haystack = f"{name} {description[:120]}"
    for pattern, level in _LEVEL_HINTS:
        if pattern.search(haystack):
            return level
    return 2


def origin_allowed(origin: str | None, prefixes: tuple[str, ...]) -> tuple[bool, str]:
    """Extension origins only. `None` is allowed only for native/tests (still needs the token)."""
    if origin is None or origin == "":
        return True, "native client (no Origin header)"
    lowered = origin.lower()
    if any(lowered.startswith(p.lower()) for p in prefixes):
        return True, "extension origin"
    return False, (f"Origin '{origin}' rejected: only browser-extension origins may connect. "
                   "A web page cannot be allowed to drive Roblox Studio.")


@dataclass
class RateLimiter:
    """Simple sliding window; protects against runaway agent loops."""

    max_per_minute: int = 240
    _events: deque = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self._events = deque()

    def allow(self) -> bool:
        now = time.monotonic()
        while self._events and now - self._events[0] > 60:
            self._events.popleft()
        if len(self._events) >= self.max_per_minute:
            return False
        self._events.append(now)
        return True


class AuditLog:
    """Append-only JSONL audit. Never raises into the request path."""

    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event: str, **fields: Any) -> None:
        record = {"ts": datetime.now(timezone.utc).isoformat(), "event": event, **fields}
        try:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, default=str) + "\n")
        except OSError:
            pass

    def tail(self, limit: int = 50) -> list[dict[str, Any]]:
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()[-limit:]
        except OSError:
            return []
        out: list[dict[str, Any]] = []
        for line in lines:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out


def check_token(provided: str, expected: str) -> bool:
    if not provided or not expected:
        return False
    return secrets.compare_digest(provided, expected)


# ---- argument validation against the real MCP JSON schema ------------------------------

_JSON_TYPES = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
    "null": type(None),
}


class ArgumentError(ValueError):
    pass


def validate_arguments(schema: dict[str, Any] | None, args: dict[str, Any] | None) -> dict[str, Any]:
    """Validate arguments against the schema published by the official Studio MCP server."""
    args = dict(args or {})
    if not isinstance(args, dict):
        raise ArgumentError("arguments must be a JSON object")
    if not schema:
        return args
    properties: dict[str, Any] = schema.get("properties") or {}
    required: list[str] = schema.get("required") or []
    missing = [key for key in required if args.get(key) is None]
    if missing:
        raise ArgumentError(f"missing required argument(s): {', '.join(missing)}")
    for key, value in args.items():
        spec = properties.get(key)
        if spec is None:
            if schema.get("additionalProperties") is False:
                raise ArgumentError(f"unknown argument '{key}' (schema forbids additional properties)")
            continue
        expected = spec.get("type")
        if isinstance(expected, list):  # e.g. ["string", "null"]
            expected = next((t for t in expected if t != "null"), None)
        py_type = _JSON_TYPES.get(expected or "")
        if py_type is not None and value is not None and not isinstance(value, py_type):
            if expected in ("integer", "number") and isinstance(value, str):
                try:
                    args[key] = int(value) if expected == "integer" else float(value)
                    value = args[key]
                except ValueError:
                    raise ArgumentError(f"argument '{key}' must be {expected}") from None
            if not isinstance(value, py_type):
                raise ArgumentError(f"argument '{key}' must be {expected}, got {type(value).__name__}")
        if spec.get("enum") and value not in spec["enum"]:
            raise ArgumentError(f"argument '{key}' must be one of {spec['enum']}")
    return args
