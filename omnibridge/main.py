"""OMNIBRIDGE entrypoint: serve (HTTP/stdio/both), diagnose, init, tools, call, test."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from .config import Config, load_config
from .core.app import OmniBridge
from .core.logger import log, setup_logging
from .mcp_server import build_mcp_server


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


async def _serve_http(bridge: OmniBridge, cfg: Config) -> None:
    import uvicorn

    from .http_api import create_http_app

    app = create_http_app(bridge, cfg)
    server = uvicorn.Server(uvicorn.Config(app, host=cfg.http_host, port=cfg.http_port,
                                           log_config=None, access_log=False, lifespan="on"))
    await server.serve()


async def _serve_stdio(bridge: OmniBridge, cfg: Config) -> None:
    mcp = build_mcp_server(bridge, cfg)
    await mcp.run_stdio_async()


async def cmd_serve(cfg: Config, args: argparse.Namespace) -> int:
    cfg.ensure_token()
    bridge = OmniBridge(cfg)
    transport = args.transport or cfg.transport
    log.info("omnibridge starting", extra={"transport": transport, "tools": bridge.registry.size,
                                           "permissionLevel": cfg.permission_level,
                                           "workspace": str(cfg.workspace_root)})
    print(f"OMNIBRIDGE AI 1.0.0 · {bridge.registry.size} tools · permission level {cfg.permission_level}",
          file=sys.stderr)
    if transport in ("http", "both"):
        print(f"  HTTP + dashboard : http://{cfg.http_host}:{cfg.http_port}", file=sys.stderr)
        print(f"  MCP Streamable   : http://{cfg.http_host}:{cfg.http_port}/mcp", file=sys.stderr)
        print(f"  Token            : {cfg.token}", file=sys.stderr)
        print(f"  Token file       : {cfg.data_dir / 'token.txt'}", file=sys.stderr)
    if transport in ("stdio", "both"):
        print("  MCP stdio        : ready (stdout reserved for JSON-RPC)", file=sys.stderr)

    if transport == "stdio":
        await _serve_stdio(bridge, cfg)
        await bridge.close()
        return 0
    if transport == "http":
        try:
            await _serve_http(bridge, cfg)
        finally:
            await bridge.close()
        return 0

    # both
    http_task = asyncio.create_task(_serve_http(bridge, cfg))
    try:
        if sys.stdin.isatty():
            log.warning("stdio disabled for 'both' transport: stdin is a TTY",
                        extra={"hint": "pipe JSON-RPC on stdin or use --transport http"})
            await http_task
        else:
            await asyncio.gather(http_task, _serve_stdio(bridge, cfg))
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        http_task.cancel()
        await bridge.close()
    return 0


async def cmd_diagnose(cfg: Config, args: argparse.Namespace) -> int:
    bridge = OmniBridge(cfg)
    try:
        result = await bridge.call_tool("system_diagnostics", {})
    finally:
        await bridge.close()
    print("=== OMNIBRIDGE DIAGNOSTICS ===")
    for check in result["checks"]:
        mark = "PASS" if check["ok"] else "FAIL"
        print(f"[{mark}] {check['name']}: {check['detail']}")
    print("=== ALL CHECKS PASSED ===" if result["ok"] else "=== SOME CHECKS FAILED ===")
    return 0 if result["ok"] else 1


async def cmd_init(cfg: Config, args: argparse.Namespace) -> int:
    cfg.ensure_token()
    bridge = OmniBridge(cfg)
    try:
        res = await bridge.call_tool("knowledge_index_luau", {})
        print(f"data dir  : {cfg.data_dir}")
        print(f"token file: {cfg.data_dir / 'token.txt'}")
        print(f"workspace : {cfg.workspace_root}")
        print(f"tools     : {bridge.registry.size}")
        print(f"luau kb   : {res['chunks']} chunks indexed")
    finally:
        await bridge.close()
    return 0


async def cmd_tools(cfg: Config, args: argparse.Namespace) -> int:
    bridge = OmniBridge(cfg)
    try:
        catalogue = bridge.tool_catalogue()
        if args.category:
            catalogue = [t for t in catalogue if t["category"] == args.category]
        if args.json:
            _print({"count": bridge.registry.size, "tools": catalogue})
            return 0
        for t in catalogue:
            print(f"L{t['level']} [{t['category']:10}] {t['name']}")
        print(f"\n{bridge.registry.size} tools total")
    finally:
        await bridge.close()
    return 0


async def cmd_call(cfg: Config, args: argparse.Namespace) -> int:
    bridge = OmniBridge(cfg)
    try:
        payload = json.loads(args.args) if args.args else {}
        result = await bridge.call_tool(args.tool, payload, confirmed=args.confirm)
        _print(result)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    finally:
        await bridge.close()
    return 0


async def cmd_test(cfg: Config, args: argparse.Namespace) -> int:
    bridge = OmniBridge(cfg)
    try:
        result = await bridge.call_tool("system_self_test", {})
    finally:
        await bridge.close()
    for check in result["checks"]:
        mark = "PASS" if check["ok"] else "FAIL"
        detail = check.get("summary") or check.get("error", "")
        print(f"[{mark}] {check['tool']}: {str(detail)[:140]}")
    print(f"\n{result['toolCount']} tools registered · self test {'PASSED' if result['ok'] else 'FAILED'}")
    return 0 if result["ok"] else 1


async def cmd_webai(cfg: Config, args: argparse.Namespace) -> int:
    from .webai import build_prompt, check_remote_mcp, openai_tools, run_calls

    bridge = OmniBridge(cfg)
    try:
        if args.check:
            result = await check_remote_mcp(args.check, token=args.token or cfg.token)
            _print(result)
            return 0 if result["chatgptReady"] else 1
        if args.openai_tools:
            _print({"count": bridge.registry.size, "tools": openai_tools(bridge)})
            return 0
        if args.run:
            text = sys.stdin.read() if args.run == "-" else Path(args.run).expanduser().read_text(encoding="utf-8")
            result = await run_calls(bridge, text, confirm=args.confirm)
            print(result.get("block") or f"ERROR: {result.get('error')}", end="" if result.get("block") else "\n")
            if result.get("parseErrors"):
                print("Parse warnings: " + "; ".join(result["parseErrors"]), file=sys.stderr)
            return 0 if result["ok"] else 1
        categories = [c.strip() for c in (args.categories or "").split(",") if c.strip()] or None
        prompt = build_prompt(bridge, args.budget or 7000, categories)
        if args.json:
            _print(prompt)
        else:
            print(prompt["prompt"])
            print(f"\n<!-- {prompt['chars']} chars · {len(prompt['tools'])} tools · "
                  f"{prompt['toolsOmitted']} omitted -->", file=sys.stderr)
        return 0
    finally:
        await bridge.close()


COMMANDS = {"serve": cmd_serve, "diagnose": cmd_diagnose, "init": cmd_init,
            "tools": cmd_tools, "call": cmd_call, "test": cmd_test, "webai": cmd_webai}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="omnibridge", description="OMNIBRIDGE AI — Universal MCP (Python core)")
    p.add_argument("command", nargs="?", default="serve", choices=sorted(COMMANDS),
                   help="serve (default) | diagnose | init | tools | call | test")
    p.add_argument("--transport", choices=["stdio", "http", "both"], default=None)
    p.add_argument("--stdio", action="store_true", help="shorthand for --transport stdio")
    p.add_argument("--port", type=int, default=None)
    p.add_argument("--host", default=None)
    p.add_argument("--workspace", default=None)
    p.add_argument("--level", type=int, choices=[1, 2, 3, 4], default=None)
    p.add_argument("--tool", default=None, help="tool name for the 'call' command")
    p.add_argument("--args", default=None, help="JSON arguments for the 'call' command")
    p.add_argument("--confirm", action="store_true", help="confirm a level-4 operation")
    p.add_argument("--category", default=None, help="filter for the 'tools' command")
    p.add_argument("--prompt", action="store_true", help="webai: print the paste-ready prompt")
    p.add_argument("--run", metavar="FILE", default=None,
                   help="webai: execute the tool calls found in FILE ('-' reads stdin)")
    p.add_argument("--check", metavar="URL", default=None,
                   help="webai: verify a public HTTPS MCP endpoint (ChatGPT readiness)")
    p.add_argument("--openai-tools", action="store_true",
                   help="webai: print OpenAI-compatible function definitions")
    p.add_argument("--budget", type=int, default=None, help="webai: prompt character budget")
    p.add_argument("--categories", default=None, help="webai: comma-separated category filter")
    p.add_argument("--token", default=None, help="token for --check")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    return p


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    args = build_parser().parse_args(argv)
    overrides: dict = {}
    if args.transport:
        overrides["transport"] = args.transport
    if args.stdio:
        overrides["transport"] = "stdio"
    if args.port:
        overrides["http_port"] = args.port
    if args.host:
        overrides["http_host"] = args.host
    if args.workspace:
        overrides["workspace_root"] = Path(args.workspace).expanduser().resolve()
    if args.level:
        overrides["permission_level"] = args.level
    cfg = load_config(**overrides)
    if args.command == "call" and not args.tool:
        print("ERROR: --tool is required for the 'call' command", file=sys.stderr)
        return 2
    try:
        return asyncio.run(COMMANDS[args.command](cfg, args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
