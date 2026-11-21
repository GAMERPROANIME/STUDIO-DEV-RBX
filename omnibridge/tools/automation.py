"""Process/automation tools (level 4: explicit confirmation required)."""
from __future__ import annotations

import asyncio
import shutil
import sys
from pathlib import Path

from ..core.permissions import ToolDef
from ..core.registry import Registry
from ..core.sandbox import sandbox_resolve

# Fixed allowlist. No shell, no arbitrary commands, no interpolation.
ALLOWED: dict[str, list[str]] = {
    "pytest": [sys.executable, "-m", "pytest", "-q"],
    "python_version": [sys.executable, "--version"],
    "npm_build": ["npm", "run", "build"],
    "npm_test": ["npm", "test", "--silent"],
    "npm_install": ["npm", "install"],
    "rojo_build": ["rojo", "build", "default.project.json", "--output", "build.rbxlx"],
    "rojo_serve": ["rojo", "serve", "default.project.json"],
    "git_status": ["git", "status", "--short"],
    "git_log": ["git", "log", "--oneline", "-n", "10"],
}


def register_automation_tools(reg: Registry) -> None:
    async def process_run(args: dict, ctx) -> dict:
        action = str(args["action"])
        if action not in ALLOWED:
            raise ValueError(f"Command not allowlisted: {action}. Allowed: {', '.join(ALLOWED)}. "
                             "Add a new entry to ALLOWED in omnibridge/tools/automation.py if needed.")
        cmd = list(ALLOWED[action])
        abs_path = sandbox_resolve(ctx.config.workspace_root, str(args.get("path", ".")))
        if not abs_path.is_dir():
            raise ValueError(f"Working directory not found: {args.get('path')}")
        if not shutil.which(cmd[0]):
            raise RuntimeError(f"Executable not found on PATH: {cmd[0]}")
        timeout_s = float(args.get("timeoutMs", 120_000)) / 1000.0
        proc = await asyncio.create_subprocess_exec(
            *cmd, cwd=str(abs_path),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
        except asyncio.TimeoutError:
            proc.kill()
            raise TimeoutError(f"'{action}' exceeded {timeout_s}s and was killed") from None
        code = proc.returncode
        return {"action": action, "command": cmd, "cwd": str(abs_path), "exitCode": code,
                "passed": code == 0, "stdout": stdout.decode(errors="replace")[-40_000:],
                "stderr": stderr.decode(errors="replace")[-20_000:]}

    async def process_list(args: dict, ctx) -> dict:
        return {"allowlistedActions": {k: " ".join(v) for k, v in ALLOWED.items()},
                "note": "process_run executes only these commands, with no shell and no user-controlled arguments."}

    async def tool_self_test(args: dict, ctx) -> dict:
        """Real end-to-end smoke test: calls several tools for real and reports outcomes."""
        checks: list[dict] = []
        probes = [
            ("system_health", {}),
            ("file_list", {"path": ".", "maxDepth": 1}),
            ("knowledge_stats", {}),
            ("agent_list_roles", {}),
            ("plugin_list", {}),
            ("roblox_inspect_project", {"path": "."}),
        ]
        for name, probe_args in probes:
            try:
                res = await ctx.call_tool(name, probe_args)
                checks.append({"tool": name, "ok": True, "summary": str(res)[:160]})
            except Exception as e:  # noqa: BLE001
                checks.append({"tool": name, "ok": False, "error": str(e)})
        return {"ok": all(c["ok"] for c in checks), "checks": checks, "toolCount": reg.size}

    reg.register(ToolDef("process_run",
                         "Run an allowlisted development command (pytest, npm build/test/install, rojo, git "
                         "status/log) inside the workspace. No shell, no arbitrary arguments. Level 4: "
                         "requires confirm=true.",
                         {"action": {"type": "string", "enum": sorted(ALLOWED)},
                          "path": {"type": "string", "default": "."},
                          "timeoutMs": {"type": "integer", "default": 120000, "minimum": 1000, "maximum": 600000}},
                         ["action"], 4, "automation", False, process_run))
    reg.register(ToolDef("process_list_actions",
                         "List the allowlisted process actions available to process_run, with their exact commands.",
                         {}, [], 1, "automation", True, process_list))
    reg.register(ToolDef("system_self_test",
                         "Run a real end-to-end self test: invokes core tools for real and reports per-tool "
                         "pass/fail. Use to verify the installation actually works.",
                         {}, [], 1, "automation", True, tool_self_test))
