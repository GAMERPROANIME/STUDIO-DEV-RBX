"""Roblox connection state machine — six states, derived from evidence only.

  studio_closed            → the official MCP server is not installed/startable (no launch spec)
  mcp_disabled             → the server answered earlier, then went away (MCP stopped in Studio)
  mcp_unreachable          → the command exists but the handshake/request failed or timed out
  no_tools                 → connected, but tools/list stays empty after every retry
  studio_open_no_project   → connected with tools, yet the server reports no open Studio
  ready                    → connected, tools discovered, Studio reachable

No OS process scanning and no guessing: each state comes from something the MCP server
actually told us (launch resolution, handshake, tools/list, studio listing tool).
OMNIBRIDGE never invents Roblox tools.
"""
from __future__ import annotations

import json
import platform
from typing import Any

from .mcp_client import MCPFailure, StudioMCPClient
from .process_manager import describe_missing

STATE_READY = "ready"
STATE_NO_TOOLS = "no_tools"
STATE_MCP_DISABLED = "mcp_disabled"
STATE_MCP_UNREACHABLE = "mcp_unreachable"
STATE_OPEN_NO_PROJECT = "studio_open_no_project"
STATE_STUDIO_CLOSED = "studio_closed"

ALL_STATES = (STATE_READY, STATE_NO_TOOLS, STATE_MCP_DISABLED, STATE_MCP_UNREACHABLE,
              STATE_OPEN_NO_PROJECT, STATE_STUDIO_CLOSED)

_STATE_HINTS = {
    STATE_STUDIO_CLOSED: (
        "Roblox Studio's own MCP server could not be launched. Install/update Studio, open "
        "Assistant → Settings → MCP Servers → enable 'Enable Studio as MCP server', or point "
        "ROBLOX_STUDIO_MCP_COMMAND at it. OMNIBRIDGE never simulates Roblox tools."
    ),
    STATE_OPEN_NO_PROJECT: (
        "The Studio MCP server is reachable but reports no open Studio instance. Open a place "
        "(.rbxl) in Roblox Studio, then refresh."
    ),
    STATE_MCP_DISABLED: (
        "The MCP server answered earlier and then stopped. In Studio: Assistant → Settings → "
        "MCP Servers → enable 'Enable Studio as MCP server', then press Restart MCP."
    ),
    STATE_MCP_UNREACHABLE: (
        "The MCP server process could not be reached (it exited, or its handshake never "
        "finished). Restart Roblox Studio, then press Restart MCP."
    ),
    STATE_NO_TOOLS: (
        "The official MCP server connected but returned an empty tool list after every retry. "
        "Update Roblox Studio; the bridge refuses to invent tools."
    ),
    STATE_READY: "Connected to the official Roblox Studio MCP server.",
}

_STUDIO_LIST_KEYS = ("list_roblox_studios", "list_studios", "get_roblox_studios")


def state_hint(state: str) -> str:
    return _STATE_HINTS.get(state, "")


class RobloxConnector:
    """Owns connection state and tool discovery for the Studio MCP link."""

    def __init__(self, client: StudioMCPClient):
        self.client = client
        self.state = STATE_STUDIO_CLOSED
        self.detail = ""
        self.studio_count: int | None = None
        self._ever_connected = False
        self._lost_after_connect = False

    # ------------------------------------------------------------------ connect
    async def connect(self, force: bool = False) -> str:
        if self.client.connected and self.client.tools and not force:
            self.state = await self._refine_ready()
            return self.state
        spec = self.client.launch
        if not spec.command:
            self.state = STATE_STUDIO_CLOSED
            self.detail = describe_missing(spec)
            return self.state

        was_connected = self._ever_connected
        tools = await self.client.discover()
        if tools:
            self._ever_connected = True
            self._lost_after_connect = False
            self.detail = ""
            self.state = await self._refine_ready()
            return self.state

        self.state = self._classify_failure(self.client.last_error, was_connected)
        self.detail = self.client.last_error
        return self.state

    def _classify_failure(self, error: str, was_connected: bool) -> str:
        lowered = (error or "").lower()
        if ("not found" in lowered or "not_configured" in lowered
                or "no such file" in lowered or "cannot find the file" in lowered):
            return STATE_STUDIO_CLOSED
        if self.client.connected:
            # Handshake worked, the server simply exposes nothing → do not fake tools.
            return STATE_NO_TOOLS
        if was_connected:
            self._lost_after_connect = True
            return STATE_MCP_DISABLED
        return STATE_MCP_UNREACHABLE

    async def _refine_ready(self) -> str:
        """`ready` unless the server itself says no Studio is open."""
        try:
            listing = await self.client.studio_state()
        except Exception:  # noqa: BLE001 - refinement must never break the connection
            return STATE_READY
        studios = _extract_studios(listing)
        if studios is None:
            self.studio_count = None
            return STATE_READY
        self.studio_count = len(studios)
        return STATE_OPEN_NO_PROJECT if not studios else STATE_READY

    # ------------------------------------------------------------------ tools
    async def refresh_tools(self) -> list[Any]:
        if not self.client.connected:
            await self.connect()
        if not self.client.connected:
            return []
        try:
            tools = await self.client.list_tools()
            if tools:
                self._ever_connected = True
            return tools
        except MCPFailure as exc:
            self.detail = exc.message
            self.state = self._classify_failure(exc.message, self._ever_connected)
            return []

    async def restart(self) -> str:
        try:
            await self.client.restart()
            self._ever_connected = True
            self._lost_after_connect = False
        except MCPFailure as exc:
            self.state = self._classify_failure(f"{exc.code} {exc.message}", self._ever_connected)
            self.detail = exc.message
            return self.state
        return await self.connect(force=True)

    # ------------------------------------------------------------------ status
    def status(self) -> dict[str, Any]:
        client = self.client
        return {
            "state": self.state,
            "hint": state_hint(self.state),
            "detail": self.detail,
            "platform": platform.system(),
            "launchCommand": client.launch.display,
            "launchSource": client.launch.source,
            "connected": client.connected,
            "serverInfo": client.server_info,
            "toolCount": len(client.tools),
            "studioCount": self.studio_count,
            "discoveryAttempts": client.discovery_attempts_used,
        }


def _extract_studios(listing: Any) -> list[Any] | None:
    """Pull the studio list out of whatever the official tool returned (None if unrelated)."""
    if not isinstance(listing, dict):
        return None
    payload = listing.get("studios")
    if isinstance(payload, list):
        return payload
    candidate = listing.get("result")
    if isinstance(candidate, dict):
        for key in ("studios", "instances", "roblox_studios"):
            value = candidate.get(key)
            if isinstance(value, list):
                return value
    text = listing.get("text")
    if isinstance(text, str):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, dict):
            for key in ("studios", "instances", "roblox_studios"):
                value = parsed.get(key)
                if isinstance(value, list):
                    return value
    return None
