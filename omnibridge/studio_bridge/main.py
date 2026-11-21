"""Entry point: `python -m omnibridge.studio_bridge` (or `python -m python_bridge`).

Boots the whole chain except the browser side:

    config → audit → MCP client (official Studio server) → connector → registry
           → connection manager → WebSocket server on ws://127.0.0.1:17613

Startup never crashes without the Studio MCP server: the bridge stays reachable, reports an
explicit state (`studio_closed`, `mcp_disabled`, …) and retries discovery in the background.
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import signal
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from .config import DEFAULT_PORT, BridgeConfig, load_config
from .connection_manager import ConnectionManager
from .mcp_client import StudioMCPClient
from .roblox_connector import RobloxConnector
from .security import AuditLog
from .tool_registry import Registry
from .websocket_server import BridgeServer

log = logging.getLogger("omnibridge.studio_bridge")


def setup_logging(cfg: BridgeConfig, verbose: bool = False) -> None:
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    level = logging.DEBUG if verbose else logging.INFO
    root = logging.getLogger("omnibridge")
    root.setLevel(level)
    if not root.handlers:
        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
        root.addHandler(console)
        try:
            rotating = RotatingFileHandler(cfg.data_dir / "studio_bridge.log", maxBytes=2_000_000,
                                           backupCount=3, encoding="utf-8")
            rotating.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
            root.addHandler(rotating)
        except OSError:
            pass


class StudioBridge:
    """Composition root; also used by tests with an injected config."""

    def __init__(self, cfg: BridgeConfig):
        self.cfg = cfg
        cfg.validate()
        cfg.ensure_token()
        self.audit = AuditLog(cfg.audit_file)
        self.client = StudioMCPClient(cfg)
        self.registry = Registry()
        self.connector = RobloxConnector(self.client)
        self.manager = ConnectionManager(cfg, self.client, self.registry, self.connector, self.audit)
        self.server = BridgeServer(cfg, self.manager, self.audit)
        self._refresh_task: asyncio.Task | None = None

    async def bootstrap(self, eager: bool = True) -> None:
        await self.server.start()
        log.info("Studio Bridge listening on %s (protocol 1)", self.cfg.uri)
        if eager:
            asyncio.create_task(self._initial_connect(), name="bridge-initial-connect")
        self._refresh_task = asyncio.create_task(self._refresh_loop(), name="bridge-refresh")

    async def _initial_connect(self) -> None:
        state = await self.connector.connect()
        if state == "ready":
            self.registry.refresh(self.client.tools)
            log.info("Studio MCP ready: %d tools from %s", len(self.registry),
                     self.client.launch.display)
        else:
            log.warning("Studio MCP not ready: %s — %s", state, self.connector.status()["hint"])
        self.server.broadcast_state()

    async def _refresh_loop(self) -> None:
        """Keeps state honest: retries discovery when disconnected, re-syncs the tool list."""
        while True:
            await asyncio.sleep(25)
            try:
                if not self.client.connected:
                    previous = self.connector.state
                    state = await self.connector.connect(force=True)
                    if state == "ready":
                        self.registry.refresh(self.client.tools)
                        log.info("Studio MCP recovered with %d tools", len(self.registry))
                    if state != previous:
                        self.server.broadcast_state()
                else:
                    tools = await self.client.list_tools()
                    names = {t.name for t in tools}
                    if names != set(self.registry.names()):
                        self.registry.refresh(tools)
                        log.info("Studio tool set changed: %d tools", len(self.registry))
                        self.server.broadcast_state()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - background loop must survive
                log.debug("refresh loop error", exc_info=True)

    async def run(self, eager: bool = True) -> None:
        await self.bootstrap(eager=eager)
        stop = asyncio.Event()

        def _signal(*_: Any) -> None:
            stop.set()

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(NotImplementedError, RuntimeError):
                loop.add_signal_handler(sig, _signal)
        try:
            await stop.wait()
        finally:
            await self.shutdown()

    async def shutdown(self) -> None:
        log.info("shutting down Studio Bridge")
        if self._refresh_task:
            self._refresh_task.cancel()
            with contextlib.suppress(BaseException):
                await self._refresh_task
        await self.server.stop()
        await self.client.stop()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="omnibridge-studio-bridge",
        description="OMNIBRIDGE Studio Bridge — local bridge between browser AI extensions and "
                    "the official Roblox Studio MCP server (ws://127.0.0.1:17613).",
    )
    parser.add_argument("--host", default=None, help="must stay 127.0.0.1")
    parser.add_argument("--port", type=int, default=None, help=f"default {DEFAULT_PORT}")
    parser.add_argument("--token", default=None, help="pairing token (default: stored/random)")
    parser.add_argument("--print-token", action="store_true", help="print the pairing token and exit")
    parser.add_argument("--permission-level", type=int, default=None, choices=[1, 2, 3, 4],
                        help="1 read-only … 4 code execution (default 3)")
    parser.add_argument("--studio-command", default=None,
                        help="explicit Studio MCP command (default: auto-discovery)")
    parser.add_argument("--studio-arg", action="append", default=None,
                        help="argument for the Studio MCP command (repeatable)")
    parser.add_argument("--check", action="store_true",
                        help="print the resolved configuration/state as JSON and exit")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = load_config(host=args.host, port=args.port, token=args.token,
                      permission_level=args.permission_level,
                      studio_command=args.studio_command,
                      studio_args=args.studio_arg or None)
    setup_logging(cfg, args.verbose)
    try:
        cfg.validate()
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.print_token:
        print(cfg.ensure_token())
        return 0
    bridge = StudioBridge(cfg)
    if args.check:
        print(json.dumps({
            "uri": cfg.uri,
            "host": cfg.host,
            "port": cfg.port,
            "permissionLevel": cfg.permission_level,
            "dataDir": str(cfg.data_dir),
            "tokenFile": str(cfg.token_file),
            "launch": {"command": bridge.client.launch.display,
                       "source": bridge.client.launch.source},
            "state": bridge.connector.status(),
        }, indent=2))
        return 0
    try:
        asyncio.run(bridge.run())
    except KeyboardInterrupt:  # pragma: no cover
        pass
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
