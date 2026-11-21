"""Desktop Bridge: native messaging framing + command handling (no browser needed)."""
from __future__ import annotations

import io
import json
import struct

import pytest

from omnibridge.bridge import native_host
from omnibridge.bridge.native_host import CoreClient, handle, read_message, write_message


class StubCore(CoreClient):
    """No network: records calls and answers deterministically."""

    def __init__(self):  # noqa: D401 - intentionally skips the real constructor
        self.base_url = "http://stub"
        self.calls: list[tuple[str, str, dict | None]] = []
        self.reachable = True

    def ensure_core(self) -> bool:  # type: ignore[override]
        return self.reachable

    def request(self, method: str, path: str, json_body: dict | None = None):
        self.calls.append((method, path, json_body))
        if path in ("/api/health", "/api/info"):
            return {"ok": True, "toolCount": 71}
        if path == "/api/tools":
            return {"count": 1, "tools": [{"name": "system_health", "level": 1, "category": "system"}]}
        if path == "/api/tools/call":
            return {"ok": True, "tool": json_body["name"], "result": {"echo": json_body["args"]}}
        return {"ok": True}

    def close(self) -> None:
        pass


def frame(payload: dict) -> bytes:
    body = json.dumps(payload).encode()
    return struct.pack("<I", len(body)) + body


def test_framing_roundtrip():
    buf = io.BytesIO(frame({"id": 1, "command": "ping"}))
    assert read_message(buf) == {"id": 1, "command": "ping"}
    out = io.BytesIO()
    write_message(out, {"ok": True})
    out.seek(0)
    assert read_message(out) == {"ok": True}


def test_framing_rejects_oversized():
    buf = io.BytesIO(struct.pack("<I", 10 * 1024 * 1024))
    with pytest.raises(ValueError):
        read_message(buf)


def test_ping_and_status():
    core = StubCore()
    assert handle(core, {"id": 1, "command": "ping"})["ok"] is True
    status = handle(core, {"id": 2, "command": "status"})
    assert status["ok"] is True
    assert status["result"]["core"]["toolCount"] == 71


def test_call_forwards_tool_arguments():
    core = StubCore()
    res = handle(core, {"id": 3, "command": "call",
                        "payload": {"name": "knowledge_stats", "args": {"limit": 2}}})
    assert res["ok"] is True
    method, path, body = core.calls[-1]
    assert (method, path) == ("POST", "/api/tools/call")
    assert body == {"name": "knowledge_stats", "args": {"limit": 2}, "confirm": False}


def test_forbidden_commands_are_rejected():
    core = StubCore()
    for command in ("http", "exec", "shell", "open"):
        res = handle(core, {"id": 4, "command": command, "payload": {}})
        assert res["ok"] is False
        assert "Unknown command" in res["error"]
    assert core.calls == []


def test_missing_core_is_reported():
    core = StubCore()
    core.reachable = False
    res = handle(core, {"id": 5, "command": "ping"})
    assert res["ok"] is False
    assert "not reachable" in res["error"]
    assert "python -m omnibridge --transport http" in res["error"]


def test_call_requires_tool_name():
    res = handle(StubCore(), {"id": 6, "command": "call", "payload": {}})
    assert res["ok"] is False and "payload.name" in res["error"]


def test_installer_writes_manifests(tmp_path, monkeypatch):
    from omnibridge.bridge import install

    paths = install.write_manifests(tmp_path / "bridge", ["abcdefghijklmnop"])
    chromium = json.loads(paths["chromium"].read_text())
    firefox = json.loads(paths["firefox"].read_text())
    assert chromium["allowed_origins"] == ["chrome-extension://abcdefghijklmnop/"]
    assert chromium["type"] == "stdio"
    assert firefox["allowed_extensions"] == [install.FIREFOX_ID]
    assert (tmp_path / "bridge" / ("omnibridge-host.bat" if install.sys.platform == "win32"
                                    else "omnibridge-host.sh")).exists()
    assert native_host.MAX_MESSAGE == 4 * 1024 * 1024
