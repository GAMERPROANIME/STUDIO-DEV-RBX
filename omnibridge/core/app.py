"""OMNIBRIDGE application container: wires every subsystem in one place."""
from __future__ import annotations

import inspect
from typing import Any

from ..agent.executor import TaskExecutor
from ..browser.bridge import BrowserBridge
from ..config import Config
from ..knowledge.engine import KnowledgeEngine
from ..roblox.connector import RobloxConnector
from ..tools.agent import register_agent_tools
from ..tools.automation import register_automation_tools
from ..tools.bridge import register_bridge_tools
from ..tools.browser import register_browser_tools
from ..tools.code import register_code_tools
from ..tools.files import register_file_tools
from ..tools.knowledge import register_knowledge_tools
from ..tools.plugins import register_plugin_tools
from ..tools.roblox import register_roblox_tools
from ..tools.system import register_system_tools
from ..tools.web import register_web_tools
from .db import Db
from .logger import log
from .permissions import PermissionDenied, ToolContext, check_permission
from .registry import Registry
from .validation import validate_args


class OmniBridge:
    """Single Python core. Every interface (MCP, HTTP, CLI, bridge) calls `call_tool`."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.db = Db(cfg)
        self.knowledge = KnowledgeEngine(self.db)
        self.registry = Registry()
        self.roblox = RobloxConnector(cfg)
        self.browser = BrowserBridge()
        self.executor = TaskExecutor(cfg, self.db, self.call_tool)
        self._register_all()

    def _register_all(self) -> None:
        reg = self.registry
        register_file_tools(reg)
        register_code_tools(reg)
        register_web_tools(reg)
        register_knowledge_tools(reg, self.knowledge)
        register_roblox_tools(reg, self.roblox)
        register_browser_tools(reg, self.browser)
        register_bridge_tools(reg, self.browser.status)
        register_plugin_tools(reg)
        register_automation_tools(reg)
        register_system_tools(reg, self.roblox.info, self.browser.status, self.knowledge.stats)
        register_agent_tools(reg, self.executor)
        log.info("omnibridge core ready", extra={"tools": reg.size, "categories": list(reg.categories())})

    async def call_tool(self, name: str, args: dict[str, Any] | None = None, confirmed: bool = False) -> Any:
        tool = self.registry.get(name)
        if tool is None:
            raise ValueError(f"Unknown tool: '{name}'. Call system_list_tools to see the real catalogue.")
        normalized = validate_args(tool, args)
        if confirmed and tool.level == 4:
            normalized["confirm"] = True
        check_permission(self.cfg, tool, normalized)
        ctx = ToolContext(self.cfg, self.db, self.call_tool, confirmed=normalized.get("confirm") is True)
        try:
            result = tool.handler(normalized, ctx) if tool.handler else None
            if inspect.isawaitable(result):
                result = await result
        except PermissionDenied as e:
            self.db.audit(name, tool.level, False, f"permission: {e}")
            raise
        except Exception as e:  # noqa: BLE001
            self.db.audit(name, tool.level, False, f"{type(e).__name__}: {e}")
            log.error("tool failed", extra={"tool": name, "error": str(e)})
            raise
        self.db.audit(name, tool.level, True)
        return result

    def tool_catalogue(self) -> list[dict[str, Any]]:
        return [{"name": t.name, "description": t.description, "category": t.category,
                 "level": t.level, "readOnly": t.read_only,
                 "inputSchema": {"type": "object",
                                 "properties": {k: {kk: vv for kk, vv in v.items() if kk in
                                                    ("type", "description", "default", "enum", "items",
                                                     "minimum", "maximum")}
                                                for k, v in t.params.items()},
                                 "required": t.required}}
                for t in self.registry.list()]

    async def close(self) -> None:
        await self.roblox.close()
        self.db.close()
