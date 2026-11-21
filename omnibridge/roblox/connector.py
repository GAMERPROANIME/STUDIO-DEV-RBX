"""Roblox Studio connector: official Studio MCP server (MCP client proxy) + discovery."""
from __future__ import annotations

import asyncio
import os
import platform
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from ..config import Config
from ..core.logger import log

STUDIO_SETUP_INSTRUCTIONS = "\n".join([
    "1. Install Roblox Studio and sign in, then open a place.",
    "2. In Studio: Assistant → Settings → MCP Servers → enable 'Enable Studio as MCP server'.",
    "3. Point OMNIBRIDGE at the server: set ROBLOX_STUDIO_MCP_COMMAND to the StudioMCP binary",
    "   (Windows: %LOCALAPPDATA%\\Roblox\\mcp.bat · macOS: StudioMCP inside RobloxStudio.app).",
    "4. Restart OMNIBRIDGE. roblox_list_studios should then report the open place.",
    "Alternative (no Studio needed): use a Rojo project — OMNIBRIDGE reads/edits .luau files directly.",
])


@dataclass(frozen=True)
class LaunchPlan:
    """How to start the official Studio MCP server (nothing is simulated)."""

    command: str | None = None
    args: list[str] = field(default_factory=list)
    cwd: str | None = None
    source: str = "missing"  # explicit | env | discovered | missing

    @property
    def display(self) -> str:
        return " ".join([self.command or "", *self.args]).strip()


def _wrap_windows_batch(command: str, args: list[str], system: str | None = None,
                        cwd: str | None = None) -> tuple[str, list[str], str | None, str]:
    """A .bat/.cmd cannot be spawned directly on Windows.

    Studio's own settings show `cmd.exe /c cd /d %LOCALAPPDATA%\Roblox && .\mcp.bat`, i.e. the
    script must run *inside* its folder. We reproduce that with cwd = the folder, which is the
    only form that also survives usernames containing spaces.
    """
    system = platform.system() if system is None else system
    path = Path(command)
    if system == "Windows" and path.suffix.lower() in (".bat", ".cmd"):
        return "cmd.exe", ["/c", path.name, *args], cwd or str(path.parent), "discovered"
    return command, args, cwd, "discovered"


def discover_studio_mcp_command(cfg: Config) -> LaunchPlan:
    if cfg.roblox_studio_mcp_command:
        command, args, cwd, _ = _wrap_windows_batch(
            cfg.roblox_studio_mcp_command, cfg.roblox_studio_mcp_args)
        return LaunchPlan(command=command, args=args, cwd=cwd, source="env")
    candidates: list[Path] = []
    if platform.system() == "Windows":
        local = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
        candidates.append(local / "Roblox" / "mcp.bat")
    elif platform.system() == "Darwin":
        candidates.append(Path("/Applications/RobloxStudio.app/Contents/MacOS/StudioMCP"))
        candidates.append(Path.home() / "Applications/RobloxStudio.app/Contents/MacOS/StudioMCP")
    for c in candidates:
        if c.exists():
            command, args, cwd, source = _wrap_windows_batch(str(c), [])
            return LaunchPlan(command=command, args=args, cwd=cwd, source=source)
    return LaunchPlan()


class RobloxConnector:
    """MCP client proxying the official Studio MCP server. Never duplicates Studio's tools."""

    def __init__(self, cfg: Config):
        self._cfg = cfg
        self._session: ClientSession | None = None
        self._stdio_ctx = None
        self._tools: list[str] = []
        self._lock = asyncio.Lock()

    async def info(self) -> dict[str, Any]:
        plan = discover_studio_mcp_command(self._cfg)
        if not plan.command:
            return {"available": False, "args": [], "tools": [],
                    "error": "Studio MCP command not found",
                    "setupInstructions": STUDIO_SETUP_INSTRUCTIONS}
        try:
            await self._ensure_connected(plan)
            return {"available": True, "command": plan.display, "cwd": plan.cwd,
                    "tools": self._tools, "setupInstructions": STUDIO_SETUP_INSTRUCTIONS}
        except Exception as e:  # noqa: BLE001
            return {"available": False, "command": command, "args": args, "tools": [],
                    "error": str(e), "setupInstructions": STUDIO_SETUP_INSTRUCTIONS}

    async def _ensure_connected(self, plan: LaunchPlan) -> None:
        if self._session is not None:
            return
        async with self._lock:
            if self._session is not None:
                return
            params = StdioServerParameters(command=plan.command or "", args=plan.args,
                                           cwd=plan.cwd)
            self._stdio_ctx = stdio_client(params)
            read, write = await self._stdio_ctx.__aenter__()
            session = ClientSession(read, write)
            await session.__aenter__()
            await session.initialize()
            listed = await session.list_tools()
            self._tools = [t.name for t in listed.tools]
            self._session = session
            log.info("connected to official Studio MCP",
                     extra={"command": plan.display, "cwd": plan.cwd, "tools": self._tools})

    async def call_tool(self, name: str, args: dict[str, Any]) -> Any:
        plan = discover_studio_mcp_command(self._cfg)
        if not plan.command:
            raise RuntimeError(f"Official Studio MCP server not configured. {STUDIO_SETUP_INSTRUCTIONS}")
        await self._ensure_connected(plan)
        if self._session is None:
            raise RuntimeError("Studio MCP unavailable")
        result = await self._session.call_tool(name, args)
        return result.model_dump(mode="json") if hasattr(result, "model_dump") else result

    async def list_tools(self) -> list[str]:
        info = await self.info()
        return info["tools"]

    async def close(self) -> None:
        if self._session is not None:
            try:
                await self._session.__aexit__(None, None, None)
            except Exception:  # noqa: BLE001
                pass
            self._session = None
        if self._stdio_ctx is not None:
            try:
                await self._stdio_ctx.__aexit__(None, None, None)
            except Exception:  # noqa: BLE001
                pass
            self._stdio_ctx = None
