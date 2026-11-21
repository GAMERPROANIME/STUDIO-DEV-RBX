"""Fake Studio MCP server for tests — speaks real MCP over stdio, exposes fake tools.

It is NOT a Roblox emulator: it exists only to exercise the bridge's MCP client, discovery
retries, timeouts and argument validation without Roblox Studio installed.

CLI knobs (env fallbacks in brackets, note that the MCP SDK filters the child environment)
    --empty-first       [FAKE_EMPTY_FIRST]  first tools/list returns [] (Studio still booting)
    --no-tools          [FAKE_NO_TOOLS]     every tools/list returns []
    --exit-after N      [FAKE_EXIT_AFTER]   exit after N seconds (crashed server)
"""
from __future__ import annotations

import asyncio
import os
import sys

import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

STATE = {"list_calls": 0, "calls": 0, "empty_first": False, "no_tools": False}


def _flag(name: str, env: str) -> bool:
    return name in sys.argv[1:] or os.environ.get(env) == "1"


def _value(name: str, env: str) -> str | None:
    if name in sys.argv[1:]:
        index = sys.argv.index(name)
        if index + 1 < len(sys.argv):
            return sys.argv[index + 1]
    return os.environ.get(env)

TOOLS = [
    types.Tool(
        name="list_roblox_studios",
        description="List open Roblox Studio instances (fake).",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    types.Tool(
        name="get_studio_state",
        description="Return the current place state (fake, read-only).",
        inputSchema={"type": "object", "properties": {"studio_id": {"type": "string"}},
                     "required": []},
    ),
    types.Tool(
        name="run_code",
        description="Execute Luau in Studio (fake, destructive level 4).",
        inputSchema={"type": "object", "properties": {"code": {"type": "string"}},
                     "required": ["code"], "additionalProperties": False},
    ),
    types.Tool(
        name="slow_tool",
        description="Sleep for N seconds (fake, timeout test).",
        inputSchema={"type": "object",
                     "properties": {"seconds": {"type": "number"}}, "required": []},
    ),
]


async def on_list_tools(_ctx, _params):
    STATE["list_calls"] += 1
    if STATE["no_tools"]:
        return types.ListToolsResult(tools=[])
    if STATE["empty_first"] and STATE["list_calls"] == 1:
        return types.ListToolsResult(tools=[])
    return types.ListToolsResult(tools=TOOLS)


async def on_call_tool(_ctx, params):
    STATE["calls"] += 1
    name = params.name
    args = params.arguments or {}

    def text(value: str, *, error: bool = False) -> types.CallToolResult:
        return types.CallToolResult(content=[types.TextContent(type="text", text=value)],
                                    isError=error)

    if name == "list_roblox_studios":
        return text('{"studios":[{"id":"fake-1","name":"TestPlace"}]}')
    if name == "get_studio_state":
        return text(f'{{"studio_id":"{args.get("studio_id", "fake-1")}","place":"TestPlace",'
                    f'"call":{STATE["calls"]}}}')
    if name == "run_code":
        return text(f'ran: {args.get("code", "")}')
    if name == "slow_tool":
        await asyncio.sleep(float(args.get("seconds", 5)))
        return text("slept")
    return text(f"unknown tool {name}", error=True)


async def main() -> None:
    STATE["empty_first"] = _flag("--empty-first", "FAKE_EMPTY_FIRST")
    STATE["no_tools"] = _flag("--no-tools", "FAKE_NO_TOOLS")
    exit_after = _value("--exit-after", "FAKE_EXIT_AFTER")
    if exit_after:
        asyncio.get_running_loop().call_later(float(exit_after), lambda: os._exit(3))
    server = Server("fake-studio-mcp", version="0.1.0",
                    on_list_tools=on_list_tools, on_call_tool=on_call_tool)
    options = server.create_initialization_options()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, options, raise_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())
