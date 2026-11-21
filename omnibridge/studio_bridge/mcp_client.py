"""MCP client for the official Roblox Studio server (stdio transport, official SDK).

Design notes
------------
* The SDK's `stdio_client` context manager must be entered and exited in the same task,
  so the connection owns a dedicated asyncio task. Requests are funnelled through a queue
  and executed inside that task — no cross-task stream access, clean shutdown.
* Discovery is retried with progressive backoff: Studio may still be starting when the
  MCP process is already alive, so an empty `tools/list` is not proof of failure.
* Every failure is turned into a structured code, never an exception the caller must parse.
"""
from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .config import BridgeConfig
from .process_manager import LaunchSpec, command_exists, describe_missing, discover_launch_spec


@dataclass
class ToolInfo:
    name: str
    description: str = ""
    schema: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "inputSchema": self.schema}


@dataclass
class MCPFailure(Exception):
    code: str
    message: str
    detail: str = ""

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.code}: {self.message}"

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "detail": self.detail}


class StudioMCPClient:
    """Long-lived MCP session with reconnect, timeouts and structured errors."""

    def __init__(self, cfg: BridgeConfig):
        self.cfg = cfg
        self.launch: LaunchSpec = discover_launch_spec(cfg.studio_command, cfg.studio_args)
        self.tools: list[ToolInfo] = []
        self.server_info: dict[str, Any] = {}
        self.connected = False
        self.last_error: str = ""
        self.discovery_attempts_used = 0
        self._task: asyncio.Task | None = None
        self._queue: asyncio.Queue = asyncio.Queue()
        self._ready = asyncio.Event()
        self._closing = False
        self._client_ctx = None
        self._session: ClientSession | None = None

    # ------------------------------------------------------------------ lifecycle
    def _params(self) -> StdioServerParameters:
        return StdioServerParameters(command=self.launch.command, args=list(self.launch.args),
                                     env=None)

    async def _session_loop(self) -> None:
        """Owns the stdio connection; serves requests from the queue."""
        try:
            async with stdio_client(self._params()) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    self._session = session
                    init = session.server_info if hasattr(session, "server_info") else None
                    # mcp>=2 exposes server_info on the session after initialize()
                    if init is None:
                        init = getattr(session, "server_capabilities", None)
                    self.server_info = {
                        "name": getattr(init, "name", "") if init else "",
                        "version": getattr(init, "version", "") if init else "",
                    }
                    self._ready.set()
                    while True:
                        item = await self._queue.get()
                        if item is None:
                            break
                        future, kind, payload = item
                        try:
                            if kind == "list_tools":
                                listed = await session.list_tools()
                                future.set_result(listed)
                            elif kind == "call_tool":
                                result = await session.call_tool(payload["name"], payload["arguments"])
                                future.set_result(result)
                            else:  # pragma: no cover - defensive
                                future.set_exception(MCPFailure("bad_request", f"unknown kind {kind}"))
                        except Exception as exc:  # noqa: BLE001 - forwarded to caller
                            if not future.done():
                                future.set_exception(exc)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - connection failures are state
            self.last_error = f"{type(exc).__name__}: {exc}"
        finally:
            self._session = None
            self.connected = False
            self._ready.clear()
            while not self._queue.empty():
                pending = self._queue.get_nowait()
                if pending is not None and not pending[0].done():
                    pending[0].set_exception(MCPFailure("disconnected", "Studio MCP session closed"))

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        if not self.launch.command:
            raise MCPFailure("server_not_configured", describe_missing(self.launch))
        if not command_exists(self.launch.command):
            raise MCPFailure("command_not_found",
                             f"Studio MCP command not found: {self.launch.command}",
                             describe_missing(self.launch))
        self._closing = False
        self._ready.clear()
        self._task = asyncio.create_task(self._session_loop(), name="studio-mcp-session")
        try:
            await asyncio.wait_for(self._ready.wait(), timeout=self.cfg.connect_timeout_s)
        except (asyncio.TimeoutError, TimeoutError):
            await self.stop()
            raise MCPFailure("startup_timeout",
                             f"Studio MCP did not respond within {self.cfg.connect_timeout_s}s "
                             "(is Roblox Studio running with the MCP server enabled?)",
                             self.last_error) from None
        self.connected = True

    async def stop(self) -> None:
        self._closing = True
        task, self._task = self._task, None
        if task is None:
            self.connected = False
            return
        with contextlib.suppress(Exception):
            await self._queue.put(None)  # graceful: session ends after the current request
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=8.0)
        except Exception:  # noqa: BLE001 - timeout, crash or cancellation
            task.cancel()
            with contextlib.suppress(BaseException):
                await task
        finally:
            self.connected = False
            self._ready.clear()

    async def restart(self) -> None:
        await self.stop()
        self.last_error = ""
        await self.start()

    # ------------------------------------------------------------------ requests
    async def _request(self, kind: str, payload: dict[str, Any] | None, timeout: float) -> Any:
        if not self.connected or self._session is None:
            raise MCPFailure("not_connected",
                             "Studio MCP is not connected. Start Roblox Studio with its MCP server "
                             "enabled, then run restart_mcp.",
                             self.last_error)
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        await self._queue.put((future, kind, payload or {}))
        try:
            # shield(): the request is not cancelled, so a late answer is discarded instead of
            # corrupting the stdio session. The server itself keeps working on it.
            return await asyncio.wait_for(asyncio.shield(future), timeout=timeout)
        except (asyncio.TimeoutError, TimeoutError):
            raise MCPFailure("timeout",
                             f"Studio MCP did not answer '{kind}' within {timeout:.0f}s",
                             "The tool may still be running inside Studio; later calls queue "
                             "behind it. Retry or use restart_mcp."
                             ) from None

    async def list_tools(self) -> list[ToolInfo]:
        listed = await self._request("list_tools", {}, self.cfg.connect_timeout_s)
        tools: list[ToolInfo] = []
        for tool in getattr(listed, "tools", []) or []:
            schema = getattr(tool, "input_schema", None) or getattr(tool, "inputSchema", None) or {}
            tools.append(ToolInfo(name=str(getattr(tool, "name", "")),
                                  description=str(getattr(tool, "description", "") or ""),
                                  schema=schema if isinstance(schema, dict) else {}))
        self.tools = tools
        return tools

    async def call_tool(self, name: str, arguments: dict[str, Any],
                        timeout: float | None = None) -> dict[str, Any]:
        result = await self._request("call_tool", {"name": name, "arguments": arguments},
                                     timeout or self.cfg.call_timeout_s)
        return _serialize_result(result)

    # ------------------------------------------------------------------ discovery
    async def discover(self, attempts: int | None = None,
                       backoff_s: float | None = None) -> list[ToolInfo]:
        """Progressive discovery: an empty list is retried, never treated as final."""
        attempts = attempts or self.cfg.discovery_attempts
        backoff_s = backoff_s if backoff_s is not None else self.cfg.discovery_backoff_s
        last_error = ""
        for attempt in range(1, attempts + 1):
            self.discovery_attempts_used = attempt
            try:
                if not self.connected:
                    await self.start()
                tools = await self.list_tools()
                if tools:
                    self.last_error = ""
                    return tools
                last_error = "the official server is connected but exposes no tools yet"
            except MCPFailure as exc:
                last_error = exc.message
                self.connected = False
            except Exception as exc:  # noqa: BLE001
                last_error = f"{type(exc).__name__}: {exc}"
                self.connected = False
            if attempt < attempts:
                await asyncio.sleep(backoff_s * attempt)
        self.last_error = last_error
        return []

    # ------------------------------------------------------------------ status
    async def studio_state(self) -> dict[str, Any]:
        """Ask the official server about open Studio instances, when it exposes such a tool."""
        if not self.connected:
            return {"available": False, "studios": [], "error": self.last_error or "not connected"}
        candidate = next((t for t in self.tools
                          if any(k in t.name.lower() for k in ("list_roblox_studios", "list_studios"))), None)
        if candidate is None:
            return {"available": True, "studios": [], "error": "",
                    "note": "the official server exposes no studio-listing tool"}
        try:
            result = await self.call_tool(candidate.name, {}, timeout=15.0)
            return {"available": True, "tool": candidate.name, "studios": result, "error": ""}
        except MCPFailure as exc:
            return {"available": True, "studios": [], "error": exc.message}

    def describe(self) -> dict[str, Any]:
        return {
            "connected": self.connected,
            "command": self.launch.display,
            "commandSource": self.launch.source,
            "serverInfo": self.server_info,
            "toolCount": len(self.tools),
            "discoveryAttempts": self.discovery_attempts_used,
            "lastError": self.last_error,
        }


def _serialize_result(result: Any) -> dict[str, Any]:
    """Normalize an MCP CallToolResult into plain JSON-friendly data."""
    is_error = bool(getattr(result, "is_error", False) or getattr(result, "isError", False))
    out: dict[str, Any] = {"isError": is_error}
    structured = getattr(result, "structured_content", None) or getattr(result, "structuredContent", None)
    if structured is not None:
        out["structured"] = structured
    content = getattr(result, "content", None) or []
    blocks: list[dict[str, Any]] = []
    texts: list[str] = []
    for block in content:
        block_type = getattr(block, "type", "")
        item: dict[str, Any] = {"type": block_type}
        if block_type == "text":
            item["text"] = getattr(block, "text", "")
            texts.append(item["text"])
        elif block_type == "image":
            item["mimeType"] = getattr(block, "mime_type", "")
            item["dataLength"] = len(getattr(block, "data", "") or "")
        else:
            dumped = getattr(block, "model_dump", None)
            item["raw"] = dumped() if callable(dumped) else str(block)
        blocks.append(item)
    out["content"] = blocks
    if texts:
        out["text"] = "\n".join(texts)
    if isinstance(structured, dict):
        out["result"] = structured
    elif "text" in out:
        out["result"] = out["text"]
    return out
