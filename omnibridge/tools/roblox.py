"""Roblox Studio tools: official MCP proxy (live) + Rojo disk layer. Nothing simulated."""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..core.permissions import ToolDef
from ..core.registry import Registry
from ..core.sandbox import sandbox_resolve
from ..roblox.connector import STUDIO_SETUP_INSTRUCTIONS, RobloxConnector
from ..roblox.luau import analyze_luau

_SKIP = {"node_modules", ".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache",
         ".mypy_cache", "dist", "build", "coverage"}


def _walk_luau(root: Path, directory: Path, out: list[str], depth: int) -> None:
    if depth > 6:
        return
    try:
        entries = sorted(directory.iterdir(), key=lambda p: p.name)
    except OSError:
        return
    for e in entries:
        if e.name in _SKIP:
            continue
        if e.is_dir():
            _walk_luau(root, e, out, depth + 1)
        elif e.suffix.lower() in (".luau", ".lua", ".rbxlx", ".rbxl", ".rbxm", ".json"):
            out.append(str(e.relative_to(root)))


def register_roblox_tools(reg: Registry, connector: RobloxConnector) -> None:
    async def _proxy(tool_pattern: str, args: dict) -> dict:
        info = await connector.info()
        if not info["available"]:
            return {"available": False, "setupInstructions": info["setupInstructions"]}
        tool = next((t for t in info["tools"] if re.search(tool_pattern, t, re.I)), None)
        if not tool:
            return {"available": True, "error": "Official server has no matching tool.",
                    "officialTools": info["tools"]}
        return {"available": True, "result": await connector.call_tool(tool, args)}

    async def list_studios(args: dict, ctx) -> dict:
        info = await connector.info()
        if not info["available"]:
            return {"available": False, "error": info.get("error"), "setupInstructions": info["setupInstructions"]}
        list_tool = next((t for t in info["tools"] if re.search(r"list.*studio|studio.*list", t, re.I)), None)
        studios = None
        if list_tool:
            try:
                studios = await connector.call_tool(list_tool, {})
            except Exception:  # noqa: BLE001
                studios = None
        return {"available": True, "command": info.get("command"), "officialTools": info["tools"], "studios": studios}

    async def get_state(args: dict, ctx) -> dict:
        info = await connector.info()
        if not info["available"]:
            return {"available": False, "setupInstructions": info["setupInstructions"]}
        tool = next((t for t in info["tools"] if re.search(r"state|status", t, re.I)), None)
        if not tool:
            return {"available": True, "note": "Connected, but the official server exposes no state tool.",
                    "officialTools": info["tools"]}
        return {"available": True, "state": await connector.call_tool(tool, {})}

    async def inspect_project(args: dict, ctx) -> dict:
        abs_path = sandbox_resolve(ctx.config.workspace_root, str(args.get("path", ".")))

        def read_json(name: str):
            try:
                return json.loads((abs_path / name).read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None

        project = read_json("project.json") or read_json("default.project.json")
        files: list[str] = []
        _walk_luau(abs_path, abs_path, files, 0)
        return {"path": str(args.get("path", ".")), "hasRojoProject": project is not None,
                "project": project, "files": files[:500], "fileCount": len(files)}

    async def search_scripts(args: dict, ctx) -> dict:
        abs_path = sandbox_resolve(ctx.config.workspace_root, str(args.get("path", ".")))
        pattern = re.compile(str(args["pattern"]), re.I)
        max_results = int(args.get("maxResults", 100))
        hits: list[dict] = []

        def walk(directory: Path, depth: int) -> None:
            if depth > 6 or len(hits) >= max_results:
                return
            try:
                entries = sorted(directory.iterdir(), key=lambda p: p.name)
            except OSError:
                return
            for e in entries:
                if e.name in _SKIP:
                    continue
                if e.is_dir():
                    walk(e, depth + 1)
                elif e.suffix in (".luau", ".lua"):
                    try:
                        for i, line in enumerate(e.read_text(encoding="utf-8").split("\n")):
                            if len(hits) < max_results and pattern.search(line):
                                hits.append({"file": str(e.relative_to(abs_path)), "line": i + 1,
                                             "text": line.strip()[:300]})
                    except OSError:
                        continue

        walk(abs_path, 0)
        return {"pattern": str(args["pattern"]), "count": len(hits), "hits": hits}

    async def read_script(args: dict, ctx) -> dict:
        abs_path = sandbox_resolve(ctx.config.workspace_root, str(args["path"]))
        src = abs_path.read_text(encoding="utf-8")
        return {"path": str(args["path"]), "lines": len(src.split("\n")), "source": src[:100_000],
                "analysis": [i.to_dict() for i in analyze_luau(src, str(args["path"]))]}

    async def inspect_instance(args: dict, ctx) -> dict:
        return await _proxy(r"inspect|get.*instance|instance", {"path": str(args["path"])})

    async def execute_luau(args: dict, ctx) -> dict:
        return await _proxy(r"execute|run.*code|eval", {"code": str(args["code"])})

    async def edit_scripts(args: dict, ctx) -> dict:
        result = await ctx.call_tool("file_update", {"path": str(args["path"]), "content": str(args["content"])})
        issues = [i.to_dict() for i in analyze_luau(str(args["content"]), str(args["path"]))]
        return {**result, "analysis": issues, "errorCount": sum(1 for i in issues if i["severity"] == "error")}

    async def create_objects(args: dict, ctx) -> dict:
        return await _proxy(r"create.*object|insert",
                            {"className": str(args["className"]), "parent": str(args["parent"]),
                             "properties": args.get("properties") or {}})

    async def playtest(args: dict, ctx) -> dict:
        return await _proxy(r"playtest|test", {"action": str(args.get("action", "status"))})

    async def console_output(args: dict, ctx) -> dict:
        return await _proxy(r"console|output|log", {"limit": int(args.get("limit", 100))})

    async def capture_screen(args: dict, ctx) -> dict:
        return await _proxy(r"capture|screenshot|screen", {})

    async def search_assets(args: dict, ctx) -> dict:
        return await _proxy(r"asset|store|search", {"query": str(args["query"]),
                                                    "assetType": str(args.get("assetType", "Model"))})

    reg.register(ToolDef("roblox_list_studios",
                         "List open Roblox Studio instances via the official Studio MCP server. If Studio MCP "
                         "is not configured, returns available=false with exact setup instructions.",
                         {}, [], 1, "roblox", True, list_studios))
    reg.register(ToolDef("roblox_get_studio_state",
                         "Get the state of the connected Studio instance via the official Studio MCP server.",
                         {}, [], 1, "roblox", True, get_state))
    reg.register(ToolDef("roblox_inspect_project",
                         "Inspect a Roblox/Rojo project on disk: project.json tree, .luau/.lua/.rbxlx files. "
                         "Works without Studio running.",
                         {"path": {"type": "string", "default": "."}}, [], 1, "roblox", True, inspect_project))
    reg.register(ToolDef("roblox_search_scripts",
                         "Search Luau script contents in a Rojo project on disk (regex).",
                         {"pattern": {"type": "string"}, "path": {"type": "string", "default": "."},
                          "maxResults": {"type": "integer", "default": 100, "minimum": 1, "maximum": 500}},
                         ["pattern"], 1, "roblox", True, search_scripts))
    reg.register(ToolDef("roblox_read_script",
                         "Read a Luau script file from a Rojo project on disk, with static analysis attached.",
                         {"path": {"type": "string"}}, ["path"], 1, "roblox", True, read_script))
    reg.register(ToolDef("roblox_inspect_instance",
                         "Inspect a live instance in Studio via the official MCP server. Requires Studio MCP "
                         "configured; otherwise returns setup instructions.",
                         {"path": {"type": "string", "description": "Instance path e.g. game.Workspace.Part"}},
                         ["path"], 1, "roblox", True, inspect_instance))
    reg.register(ToolDef("roblox_execute_luau",
                         "Execute Luau code in the live Studio session via the official MCP server. "
                         "Requires Studio MCP configured.",
                         {"code": {"type": "string"}}, ["code"], 3, "roblox", False, execute_luau))
    reg.register(ToolDef("roblox_edit_scripts",
                         "Edit Luau scripts on disk (Rojo project): create or overwrite script files with "
                         "backup + static analysis. For live Studio editing use roblox_execute_luau.",
                         {"path": {"type": "string"}, "content": {"type": "string"}},
                         ["path", "content"], 3, "roblox", False, edit_scripts))
    reg.register(ToolDef("roblox_create_objects",
                         "Create instances in the live Studio session via the official MCP server. "
                         "Requires Studio MCP configured.",
                         {"className": {"type": "string"}, "parent": {"type": "string"},
                          "properties": {"type": "object", "default": {}}},
                         ["className", "parent"], 3, "roblox", False, create_objects))
    reg.register(ToolDef("roblox_playtest",
                         "Start/stop a playtest in Studio via the official MCP server and return its status.",
                         {"action": {"type": "string", "default": "status", "enum": ["start", "stop", "status"]}},
                         [], 3, "roblox", False, playtest))
    reg.register(ToolDef("roblox_get_console_output",
                         "Read Studio console output (errors/warnings) via the official MCP server.",
                         {"limit": {"type": "integer", "default": 100, "minimum": 1, "maximum": 500}},
                         [], 1, "roblox", True, console_output))
    reg.register(ToolDef("roblox_capture_screen",
                         "Capture a screenshot of the Studio viewport via the official MCP server.",
                         {}, [], 1, "roblox", True, capture_screen))
    reg.register(ToolDef("roblox_search_assets",
                         "Search the Roblox Creator Store via the official MCP server when available. "
                         "Otherwise returns setup instructions — never fakes results.",
                         {"query": {"type": "string"}, "assetType": {"type": "string", "default": "Model"}},
                         ["query"], 1, "roblox", True, search_assets))
    void = STUDIO_SETUP_INSTRUCTIONS  # re-exported for docs/tests
    _ = void
