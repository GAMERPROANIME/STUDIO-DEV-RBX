#!/usr/bin/env python3
"""Minimal Studio Bridge client — proves the protocol end to end.

Usage
-----
1. start the bridge:      python -m python_bridge            (ws://127.0.0.1:17613)
2. run this script:       python examples/studio_bridge_client.py --list
                          python examples/studio_bridge_client.py --call get_studio_state \\
                                 --args '{"studio_id":"abc"}'

The script prints every frame the bridge sends, so it doubles as a protocol reference for the
browser extension. It never talks to Roblox directly: only the bridge owns the MCP session.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

try:
    from websockets.asyncio.client import connect
except ImportError:  # pragma: no cover
    print("Install websockets first: pip install websockets", file=sys.stderr)
    raise SystemExit(2)

DEFAULT_URI = os.environ.get("OMNIBRIDGE_BRIDGE_URI", "ws://127.0.0.1:17613")
DEFAULT_TOKEN_FILE = Path(os.environ.get("OMNIBRIDGE_DATA_DIR", Path.home() / ".omnibridge")) / "studio_bridge_token.txt"


def load_token(explicit: str | None) -> str:
    if explicit:
        return explicit
    env = os.environ.get("OMNIBRIDGE_BRIDGE_TOKEN") or os.environ.get("OMNIBRIDGE_TOKEN")
    if env:
        return env
    if DEFAULT_TOKEN_FILE.exists():
        return DEFAULT_TOKEN_FILE.read_text(encoding="utf-8").strip()
    raise SystemExit(f"No pairing token: run `python -m python_bridge --print-token` "
                     f"(expected in {DEFAULT_TOKEN_FILE})")


async def run(args: argparse.Namespace) -> int:
    token = load_token(args.token)
    async with connect(args.uri, origin="chrome-extension://omnibridge-cli", open_timeout=10) as ws:
        await ws.send(json.dumps({"id": "hello", "type": "hello", "token": token,
                                  "client": "examples/studio_bridge_client"}))
        first = json.loads(await ws.recv())
        print("← hello_ok:", json.dumps(first, indent=2)[:1200])
        if first.get("type") != "hello_ok":
            return 1

        requests = []
        if args.status or not (args.list or args.call):
            requests.append({"id": "1", "action": "status"})
        if args.list:
            requests.append({"id": "2", "action": "list_tools", "refresh": True})
        if args.call:
            requests.append({"id": "3", "action": "call_tool", "tool": args.call,
                             "arguments": json.loads(args.args or "{}"),
                             "timeout": args.timeout})
        for request in requests:
            await ws.send(json.dumps(request))
            while True:
                message = json.loads(await ws.recv())
                if message.get("type") == "event":
                    print(f"← event {message['event']}: state={message['data'].get('state')}")
                    continue
                print(f"← {message.get('action')}: {json.dumps(message, indent=2)[:3000]}")
                break
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Talk to the local OMNIBRIDGE Studio Bridge.")
    parser.add_argument("--uri", default=DEFAULT_URI)
    parser.add_argument("--token", default=None)
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--list", action="store_true", help="list discovered Studio MCP tools")
    parser.add_argument("--call", default=None, metavar="TOOL", help="call one Studio tool")
    parser.add_argument("--args", default=None, help="JSON arguments for --call")
    parser.add_argument("--timeout", type=float, default=60.0)
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
