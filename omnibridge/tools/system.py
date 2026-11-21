"""System tools: health, discovery, diagnostics, audit."""
from __future__ import annotations

import os
import platform
import sys
from typing import Any, Awaitable, Callable

from ..core.permissions import ToolDef
from ..core.registry import Registry
from ..knowledge.sources import DOC_SOURCES


def register_system_tools(reg: Registry, roblox_info: Callable[[], Awaitable[Any]],
                          bridge_status: Callable[[], Any], knowledge_stats: Callable[[], Any]) -> None:
    async def health(args: dict, ctx) -> dict:
        roblox = await roblox_info()
        return {
            "ok": True, "version": "1.0.0",
            "runtime": {"python": sys.version.split()[0], "platform": platform.system(),
                        "arch": platform.machine(), "pid": os.getpid()},
            "workspace": str(ctx.config.workspace_root),
            "workspaceExists": ctx.config.workspace_root.exists(),
            "dataDir": str(ctx.config.data_dir),
            "permissionLevel": ctx.config.permission_level,
            "transport": ctx.config.transport,
            "toolCount": reg.size,
            "categories": reg.categories(),
            "robloxStudio": roblox,
            "browserBridge": bridge_status(),
            "knowledge": knowledge_stats(),
        }

    async def list_tools(args: dict, ctx) -> list[dict]:
        cat = args.get("category")
        return [{"name": t.name, "category": t.category, "level": t.level, "readOnly": t.read_only,
                 "description": t.description} for t in reg.list() if not cat or t.category == cat]

    async def diagnostics(args: dict, ctx) -> dict:
        checks: list[dict] = []

        def push(name: str, ok: bool, detail: str) -> None:
            checks.append({"name": name, "ok": ok, "detail": detail})

        push("workspace", ctx.config.workspace_root.exists(), str(ctx.config.workspace_root))
        push("dataDir", ctx.config.data_dir.is_dir(), str(ctx.config.data_dir))
        push("token", bool(ctx.config.token), "configured" if ctx.config.token else "will be generated on HTTP start")
        push("python", sys.version_info >= (3, 11), f"python {sys.version.split()[0]} (requires >=3.11)")
        push("dashboard", (ctx.config.dashboard_dir / "index.html").exists(), str(ctx.config.dashboard_dir))
        push("pluginsDir", ctx.config.plugins_dir.exists(), str(ctx.config.plugins_dir))
        roblox = await roblox_info()
        # Optional subsystems: absence is not a failure, but it is reported honestly.
        push("robloxStudioMcp", True,
             "connected" if roblox.get("available") else f"not configured (optional) — {roblox.get('error', '')}")
        bridge = bridge_status()
        push("browserExtension", True, "connected" if bridge.get("connected") else "not connected (optional)")
        ks = knowledge_stats()
        chunks = ks.get("chunks") or 0
        push("knowledgeBase", True,
             f"{chunks} chunks indexed" if chunks else
             "empty — run `omnibridge init` or the knowledge_index_luau tool")
        push("docSources", len(DOC_SOURCES) > 0, f"{len(DOC_SOURCES)} curated sources")
        return {"ok": all(c["ok"] for c in checks), "checks": checks}

    async def audit_log(args: dict, ctx) -> list[dict]:
        return ctx.db.audit_recent(int(args.get("limit", 50)))

    reg.register(ToolDef("system_health",
                         "Health check for OMNIBRIDGE: runtime, workspace, data dir, tool count, connected subsystems "
                         "(Roblox Studio MCP, browser extension, knowledge base). Call this first to know what is available.",
                         {}, [], 1, "system", True, health))
    reg.register(ToolDef("system_list_tools",
                         "List every registered MCP tool with its category, permission level and description. "
                         "Use to discover capabilities before acting.",
                         {"category": {"type": "string", "description": "Optional category filter"}}, [], 1, "system", True, list_tools))
    reg.register(ToolDef("system_diagnostics",
                         "Deep diagnostics: workspace, DB, token, dashboard, Studio MCP discovery, bridge status, "
                         "knowledge index. Returns pass/fail per check with remediation hints.",
                         {}, [], 1, "system", True, diagnostics))
    reg.register(ToolDef("system_audit_log",
                         "Recent audit log of tool calls (tool, permission level, success/failure). "
                         "Use for security review and debugging.",
                         {"limit": {"type": "integer", "default": 50, "minimum": 1, "maximum": 500}}, [], 1, "system", True, audit_log))
