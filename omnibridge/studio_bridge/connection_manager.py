"""Request orchestration: validation, permissions, concurrency, timeouts, errors, audit."""
from __future__ import annotations

import asyncio
import time
from typing import Any

from .config import BridgeConfig
from .mcp_client import MCPFailure, StudioMCPClient
from .roblox_connector import RobloxConnector
from .security import (ArgumentError, AuditLog, RateLimiter, classify_tool_level, redact,
                       validate_arguments)
from .tool_registry import Registry

ERROR_CODES = {
    "unknown_tool", "invalid_arguments", "permission_denied", "not_connected", "timeout",
    "rate_limited", "tool_failed", "busy",
}


class BridgeError(Exception):
    def __init__(self, code: str, message: str, detail: str = ""):
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "detail": self.detail}


class ConnectionManager:
    def __init__(self, cfg: BridgeConfig, client: StudioMCPClient, registry: Registry,
                 connector: RobloxConnector, audit: AuditLog | None = None):
        self.cfg = cfg
        self.client = client
        self.registry = registry
        self.connector = connector
        self.audit = audit or AuditLog(cfg.audit_file)
        self.limiter = RateLimiter(cfg.max_calls_per_minute)
        self._semaphore = asyncio.Semaphore(cfg.max_concurrent_calls)
        self.inflight = 0
        self.stats = {"calls": 0, "ok": 0, "errors": 0}

    # ---------------------------------------------------------------- tools
    async def list_tools(self, refresh: bool = False) -> list[dict[str, Any]]:
        if refresh or not len(self.registry):
            tools = await self.connector.refresh_tools()
            if tools:
                self.registry.refresh(tools, now=_now())
        return self.registry.manifest()

    def _check_tool(self, name: str, arguments: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
        info = self.registry.get(name)
        if info is None:
            raise BridgeError("unknown_tool",
                              f"'{name}' is not exposed by the official Studio MCP server",
                              f"known tools: {', '.join(self.registry.names()) or '(none discovered)'}")
        if self.cfg.allowed_tools and name not in self.cfg.allowed_tools:
            raise BridgeError("permission_denied",
                              f"'{name}' is not in OMNIBRIDGE_ALLOWED_TOOLS")
        level = classify_tool_level(name, info.description)
        self.registry.levels[name] = level
        if level > self.cfg.permission_level:
            raise BridgeError(
                "permission_denied",
                f"'{name}' requires permission level {level}, bridge level is {self.cfg.permission_level}",
                "Raise OMNIBRIDGE_PERMISSION_LEVEL (max 4) after you reviewed what this tool does.")
        try:
            safe_args = validate_arguments(info.schema, arguments)
        except ArgumentError as exc:
            raise BridgeError("invalid_arguments", str(exc),
                              f"expected schema: {info.schema}") from None
        return info, safe_args

    # ---------------------------------------------------------------- calls
    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None,
                        timeout: float | None = None, source: str = "bridge") -> dict[str, Any]:
        started = time.monotonic()
        self.stats["calls"] += 1
        if not self.limiter.allow():
            self.stats["errors"] += 1
            raise BridgeError("rate_limited", f"more than {self.cfg.max_calls_per_minute} calls/min")
        try:
            info, safe_args = self._check_tool(name, dict(arguments or {}))
        except BridgeError as exc:
            self.stats["errors"] += 1
            self.audit.write("tool_rejected", tool=name, code=exc.code, reason=exc.message,
                             source=source)
            raise
        if not self.client.connected:
            raise BridgeError("not_connected", "Studio MCP is not connected",
                              f"state={self.connector.state}; {self.connector.status()['hint']}")
        if self._semaphore.locked() and self.inflight >= self.cfg.max_concurrent_calls:
            raise BridgeError("busy", "too many Roblox tool calls in flight, retry shortly")
        async with self._semaphore:
            self.inflight += 1
            self.audit.write("tool_call", tool=name, args=_truncate(safe_args), source=source,
                             level=self.registry.level_of(name))
            try:
                result = await self.client.call_tool(name, safe_args, timeout=timeout)
            except MCPFailure as exc:
                self.stats["errors"] += 1
                code = exc.code if exc.code in ERROR_CODES else "tool_failed"
                self.audit.write("tool_error", tool=name, code=code, message=exc.message)
                if exc.code == "not_connected":
                    self.connector.state = "mcp_unreachable"
                raise BridgeError(code, exc.message, exc.detail) from None
            except Exception as exc:  # noqa: BLE001 - surfaced as structured error
                self.stats["errors"] += 1
                self.audit.write("tool_error", tool=name, code="tool_failed",
                                 message=redact(str(exc)))
                raise BridgeError("tool_failed", f"{type(exc).__name__}: {exc}") from None
            finally:
                self.inflight -= 1
        elapsed = round(time.monotonic() - started, 3)
        if result.get("isError"):
            self.stats["errors"] += 1
        else:
            self.stats["ok"] += 1
        self.audit.write("tool_result", tool=name, elapsed_s=elapsed,
                         is_error=bool(result.get("isError")))
        _ = info
        return {**result, "tool": name, "elapsed": elapsed}

    # ---------------------------------------------------------------- status
    def status(self) -> dict[str, Any]:
        return {
            "bridge": "studio_bridge",
            "connected": self.client.connected,
            "state": self.connector.state,
            "toolCount": len(self.registry),
            "registryVersion": self.registry.version,
            "permissionLevel": self.cfg.permission_level,
            "inflight": self.inflight,
            "stats": self.stats,
            "mcp": self.client.describe(),
        }


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _truncate(value: Any, limit: int = 1200) -> Any:
    text = repr(value)
    return text if len(text) <= limit else text[:limit] + "…"
