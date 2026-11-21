"""Chrome/Firefox Native Messaging host — Python.

Speaks the native messaging framing (4-byte little-endian length + UTF-8 JSON)
on stdin/stdout and forwards **tool calls only** to the local OMNIBRIDGE HTTP
core. It is not an open HTTP proxy: the extension cannot ask for arbitrary URLs,
arbitrary files or arbitrary commands.

Messages in :  {"id": <any>, "command": "status"|"tools"|"call"|"ping", "payload": {...}}
Messages out:  {"id": <any>, "ok": true, "result": ...} | {"id": <any>, "ok": false, "error": "..."}
"""
from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx

MAX_MESSAGE = 4 * 1024 * 1024


def _log(msg: str, **fields: Any) -> None:
    payload = {"level": "info", "msg": msg, **fields}
    print(json.dumps(payload), file=sys.stderr, flush=True)


def read_message(stream) -> dict[str, Any] | None:
    raw_len = stream.read(4)
    if len(raw_len) < 4:
        return None
    (length,) = struct.unpack("<I", raw_len)
    if length > MAX_MESSAGE:
        raise ValueError(f"Message too large: {length} bytes")
    body = stream.read(length)
    if len(body) < length:
        return None
    return json.loads(body.decode("utf-8"))


def write_message(stream, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    stream.write(struct.pack("<I", len(body)))
    stream.write(body)
    stream.flush()


class CoreClient:
    """Talks to exactly one endpoint: the local OMNIBRIDGE core."""

    def __init__(self) -> None:
        self.base_url = os.environ.get("OMNIBRIDGE_URL", "http://127.0.0.1:8765").rstrip("/")
        self.token_file = Path(os.environ.get("OMNIBRIDGE_DATA_DIR", str(Path.home() / ".omnibridge"))) / "token.txt"
        self.autostart = os.environ.get("OMNIBRIDGE_BRIDGE_AUTOSTART", "1") != "0"
        self._client = httpx.Client(base_url=self.base_url, timeout=30.0)
        self._started: subprocess.Popen | None = None

    def token(self) -> str:
        env = os.environ.get("OMNIBRIDGE_TOKEN")
        if env:
            return env
        try:
            return self.token_file.read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    def _headers(self) -> dict[str, str]:
        token = self.token()
        return {"Authorization": f"Bearer {token}"} if token else {}

    def ensure_core(self) -> bool:
        for _ in range(2):
            try:
                r = self._client.get("/api/health", timeout=2.0)
                if r.status_code == 200:
                    return True
            except httpx.HTTPError:
                pass
            if not self.autostart or self._started is not None:
                return False
            self._start()
        return False

    def _start(self) -> None:
        cmd = [sys.executable, "-m", "omnibridge", "--transport", "http"]
        _log("starting core", command=cmd)
        env = {**os.environ, "OMNIBRIDGE_TRANSPORT": "http"}
        kwargs: dict[str, Any] = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
                                  "stdin": subprocess.DEVNULL, "env": env, "cwd": str(Path.home())}
        if sys.platform == "win32":
            kwargs["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        self._started = subprocess.Popen(cmd, **kwargs)  # noqa: S603
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                if self._client.get("/api/health", timeout=1.0).status_code == 200:
                    return
            except httpx.HTTPError:
                time.sleep(0.4)

    def request(self, method: str, path: str, json_body: dict | None = None) -> Any:
        r = self._client.request(method, path, json=json_body, headers=self._headers(), timeout=120.0)
        try:
            data = r.json()
        except ValueError:
            data = {"raw": r.text[:2000]}
        if r.status_code >= 400:
            message = data.get("detail", data) if isinstance(data, dict) else data
            raise RuntimeError(f"core returned HTTP {r.status_code}: {message}")
        return data

    def close(self) -> None:
        self._client.close()


ALLOWED_COMMANDS = {"ping", "status", "tools", "call", "health"}


def handle(core: CoreClient, message: dict[str, Any]) -> dict[str, Any]:
    msg_id = message.get("id")
    command = str(message.get("command", "")).strip()
    payload = message.get("payload") or {}
    try:
        if command not in ALLOWED_COMMANDS:
            raise ValueError(f"Unknown command '{command}'. Allowed: {sorted(ALLOWED_COMMANDS)}")
        if not core.ensure_core():
            raise RuntimeError(
                "OMNIBRIDGE core is not reachable at " + core.base_url +
                ". Start it with: python -m omnibridge --transport http")
        if command in ("ping", "health"):
            return {"id": msg_id, "ok": True, "result": core.request("GET", "/api/health")}
        if command == "status":
            return {"id": msg_id, "ok": True,
                    "result": {"core": core.request("GET", "/api/info"),
                               "roblox": core.request("GET", "/api/roblox"),
                               "browser": core.request("GET", "/api/browser/status"),
                               "recentAudit": core.request("GET", "/api/audit?limit=10")}}
        if command == "tools":
            return {"id": msg_id, "ok": True, "result": core.request("GET", "/api/tools")}
        name = str(payload.get("name", "")).strip()
        if not name:
            raise ValueError("payload.name is required for 'call'")
        args = payload.get("args") or {}
        confirm = bool(payload.get("confirm", False))
        if not isinstance(args, dict):
            raise ValueError("payload.args must be an object")
        result = core.request("POST", "/api/tools/call",
                              {"name": name, "args": args, "confirm": confirm})
        return {"id": msg_id, "ok": True, "result": result}
    except Exception as e:  # noqa: BLE001
        _log("bridge error", command=command, error=str(e))
        return {"id": msg_id, "ok": False, "error": str(e)}


def main() -> int:
    host = sys.argv[1] if len(sys.argv) > 1 else "com.omnibridge.host"
    _log("native host started", host=host, python=sys.version.split()[0])
    core = CoreClient()
    try:
        while True:
            try:
                message = read_message(sys.stdin.buffer)
            except ValueError as e:
                write_message(sys.stdout.buffer, {"id": None, "ok": False, "error": str(e)})
                continue
            if message is None:
                break
            write_message(sys.stdout.buffer, handle(core, message))
    except KeyboardInterrupt:
        pass
    finally:
        core.close()
    _log("native host stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
