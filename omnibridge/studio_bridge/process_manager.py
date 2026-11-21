"""Studio MCP process discovery and lifecycle (Windows-first, macOS/Linux aware).

Roblox ships the server itself; OMNIBRIDGE only launches and supervises it:

  Windows : cmd.exe /c %LOCALAPPDATA%\\Roblox\\mcp.bat
  macOS   : /Applications/RobloxStudio.app/Contents/MacOS/StudioMCP
  Linux   : not shipped by Roblox — an explicit command must be provided (tests, Wine, CI)
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class LaunchSpec:
    command: str
    args: list[str]
    source: str  # "env" | "discovered" | "explicit" | "missing"

    @property
    def display(self) -> str:
        return " ".join([self.command, *self.args]).strip()


def _windows_candidates() -> list[Path]:
    local = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    return [local / "Roblox" / "mcp.bat", local / "Roblox" / "MCP" / "mcp.bat"]


def _macos_candidates() -> list[Path]:
    return [
        Path("/Applications/RobloxStudio.app/Contents/MacOS/StudioMCP"),
        Path.home() / "Applications/RobloxStudio.app/Contents/MacOS/StudioMCP",
        Path("/Applications/Roblox Studio.app/Contents/MacOS/StudioMCP"),
    ]


def _linux_candidates() -> list[Path]:
    return [Path("/opt/roblox-studio/StudioMCP"), Path.home() / "RobloxStudio/StudioMCP"]


def discover_launch_spec(command: str | None = None, args: list[str] | None = None) -> LaunchSpec:
    """Resolve how to start the official server. Explicit configuration wins."""
    system = platform.system()
    if command:
        return LaunchSpec(command, list(args or []), "explicit" if not args and command else "env")
    env_cmd = os.environ.get("OMNIBRIDGE_STUDIO_MCP_COMMAND") or os.environ.get("ROBLOX_STUDIO_MCP_COMMAND")
    if env_cmd:
        env_args = (os.environ.get("OMNIBRIDGE_STUDIO_MCP_ARGS")
                    or os.environ.get("ROBLOX_STUDIO_MCP_ARGS") or "")
        return LaunchSpec(env_cmd, env_args.split(), "env")

    candidates = {"Windows": _windows_candidates, "Darwin": _macos_candidates,
                  "Linux": _linux_candidates}.get(system, _linux_candidates)()
    for candidate in candidates:
        if candidate.exists():
            if system == "Windows" and candidate.suffix.lower() in (".bat", ".cmd"):
                # .bat needs a shell; this mirrors the documented Roblox invocation.
                return LaunchSpec("cmd.exe", ["/c", str(candidate)], "discovered")
            return LaunchSpec(str(candidate), [], "discovered")
    return LaunchSpec("", [], "missing")


def describe_missing(spec: LaunchSpec) -> str:
    system = platform.system()
    if system == "Windows":
        hint = r"%LOCALAPPDATA%\Roblox\mcp.bat"
    elif system == "Darwin":
        hint = "/Applications/RobloxStudio.app/Contents/MacOS/StudioMCP"
    else:
        hint = "a Studio MCP binary or wrapper script"
    return (
        f"Official Roblox Studio MCP server not found (looked for {hint}). "
        "Open Roblox Studio → Assistant → Settings → MCP Servers → enable "
        "'Enable Studio as MCP server', then set ROBLOX_STUDIO_MCP_COMMAND if it lives elsewhere. "
        "Nothing is simulated by OMNIBRIDGE: without this server there are no real Roblox tools."
    )


def command_exists(command: str) -> bool:
    if not command:
        return False
    path = Path(command)
    if path.is_absolute() or os.sep in command:
        return path.exists()
    return shutil.which(command) is not None


def process_alive(proc: subprocess.Popen) -> bool:
    return proc.poll() is None


def python_module_command(module: str) -> list[str]:
    """Handy for tests/fixtures: run a module with the current interpreter."""
    return [sys.executable, "-m", module]
