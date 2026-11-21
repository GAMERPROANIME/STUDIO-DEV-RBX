"""MCP protocol: schema generation, tools/resources/prompts, stdio round trip."""
from __future__ import annotations

import json
import os
import sys

import pytest

from omnibridge.mcp_server import build_mcp_server, effective_params


def test_effective_params_adds_confirm_for_level4(bridge):
    tool = bridge.registry.get("process_run")
    assert "confirm" in effective_params(tool)
    assert "confirm" not in bridge.registry.get("file_read").params


def test_built_server_registers_every_tool(bridge):
    mcp = build_mcp_server(bridge)
    registered = mcp._tool_manager.list_tools()  # official SDK introspection
    names = {t.name for t in registered}
    assert names == {t.name for t in bridge.registry.list()}


def test_tool_schemas_match_registry(bridge):
    mcp = build_mcp_server(bridge)
    by_name = {t.name: t for t in mcp._tool_manager.list_tools()}
    read = by_name["file_read"]
    schema = read.parameters
    assert "path" in schema["properties"]
    assert "path" in schema["required"]
    assert schema["properties"]["limit"]["type"] == "integer"
    run_proc = by_name["process_run"]
    assert "confirm" in run_proc.parameters["properties"]
    assert by_name["system_health"].annotations.read_only_hint is True


def test_stdio_round_trip(bridge, cfg):
    """Full protocol test: spawn the real server and talk MCP to it."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    env = {**os.environ, "OMNIBRIDGE_DATA_DIR": str(cfg.data_dir),
           "OMNIBRIDGE_WORKSPACE": str(cfg.workspace_root),
           "OMNIBRIDGE_PERMISSION_LEVEL": "4", "OMNIBRIDGE_LOG_LEVEL": "ERROR"}

    async def scenario():
        params = StdioServerParameters(command=sys.executable, args=["-m", "omnibridge", "--stdio"], env=env)
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as session:
                init = await session.initialize()
                tools = await session.list_tools()
                call = await session.call_tool("system_health", {})
                denied = await session.call_tool("process_run", {"action": "python_version"})
                allowed = await session.call_tool("process_run", {"action": "python_version", "confirm": True})
                prompts = await session.list_prompts()
                resources = await session.list_resources()
                info = await session.read_resource("omnibridge://system/info")
                catalogue = await session.read_resource("omnibridge://tools/catalogue")
                unknown = await session.call_tool("nope", {})
                return init, tools, call, denied, allowed, prompts, resources, info, catalogue, unknown

    import asyncio

    init, tools, call, denied, allowed, prompts, resources, info, catalogue, unknown = asyncio.run(scenario())
    assert init.server_info.name == "omnibridge-ai"
    assert len(tools.tools) == bridge.registry.size
    assert call.is_error is False
    assert denied.is_error is True and "permission denied" in denied.content[0].text
    assert allowed.is_error is False
    assert {p.name for p in prompts.prompts} == {"roblox-game-mission", "debug-workflow"}
    uris = {str(r.uri) for r in resources.resources}
    assert "omnibridge://system/info" in uris
    assert json.loads(info.contents[0].text)["permissionLevel"] == 4
    assert json.loads(catalogue.contents[0].text)["count"] == bridge.registry.size
    assert unknown.is_error is True
