"""Tests for the OMNIBRIDGE Studio Bridge (Python side, Milestone 1).

Proofs covered here:
  * configuration refuses non-loopback binding and persists a random pairing token;
  * origin policy accepts extension origins only (a web page is refused at the handshake);
  * the pairing token gates the WebSocket (`hello` frame), constant-time compare;
  * JSON Schema validation of arguments taken from the real MCP server;
  * discovery retries with progressive backoff; empty list ≠ failure;
  * six connection states derived from evidence;
  * tool registry is dynamic (never hardcoded);
  * request queue survives a timeout, restart works, structured errors everywhere;
  * live websockets client: hello, list_tools, call_tool, status, unknown action, audit.
"""
from __future__ import annotations

import asyncio
import json
import os
import socket
import sys
import tempfile
from pathlib import Path

import pytest

from omnibridge.studio_bridge.config import BridgeConfig, load_config
from omnibridge.studio_bridge.connection_manager import BridgeError, ConnectionManager
from omnibridge.studio_bridge.mcp_client import MCPFailure, StudioMCPClient, ToolInfo
from omnibridge.studio_bridge.process_manager import discover_launch_spec
from omnibridge.studio_bridge.roblox_connector import (STATE_NO_TOOLS, STATE_READY,
                                                       STATE_STUDIO_CLOSED, RobloxConnector)
from omnibridge.studio_bridge.security import (ArgumentError, AuditLog, RateLimiter,
                                               check_token, classify_tool_level, origin_allowed,
                                               redact, validate_arguments)
from omnibridge.studio_bridge.tool_registry import Registry

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = "tests.fixtures.fake_studio_mcp"


# ----------------------------------------------------------------------------- helpers
def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def make_config(tmp_path: Path, **overrides) -> BridgeConfig:
    values = dict(
        host="127.0.0.1", port=free_port(), data_dir=tmp_path, token="test-token-123",
        studio_command=sys.executable, studio_args=["-m", FIXTURE],
        discovery_attempts=3, discovery_backoff_s=0.05, connect_timeout_s=15.0,
        call_timeout_s=8.0, permission_level=4, heartbeat_s=5.0, auth_timeout_s=2.0,
        allowed_origin_prefixes=("chrome-extension://",),
    )
    values.update(overrides)
    cfg = BridgeConfig(**values)
    cfg.validate()
    return cfg


async def stack(cfg: BridgeConfig):
    """Build client/registry/connector/manager and start the WebSocket server."""
    from omnibridge.studio_bridge.websocket_server import BridgeServer

    audit = AuditLog(cfg.audit_file)
    client = StudioMCPClient(cfg)
    registry = Registry()
    connector = RobloxConnector(client)
    manager = ConnectionManager(cfg, client, registry, connector, audit)
    server = BridgeServer(cfg, manager, audit)
    await server.start()
    return client, registry, connector, manager, server, audit


async def close(stack_tuple) -> None:
    client, _registry, _connector, _manager, server, _audit = stack_tuple
    await server.stop()
    await client.stop()


class WSClient:
    """Minimal test client for the bridge protocol."""

    def __init__(self, ws):
        self.ws = ws
        self._n = 0
        self.events: list[dict] = []

    async def raw(self) -> dict:
        """Next frame, including server-pushed events."""
        return json.loads(await asyncio.wait_for(self.ws.recv(), 20))

    async def reply(self, request_id: str | None = None) -> dict:
        """Next reply frame (server-pushed events are skipped)."""
        while True:
            message = await self.raw()
            if message.get("type") == "event":
                self.events.append(message)
                continue
            if request_id is None or message.get("id") == request_id:
                return message

    async def hello(self, token: str) -> dict:
        self._n += 1
        await self.ws.send(json.dumps({"id": f"h{self._n}", "type": "hello",
                                       "token": token, "client": "pytest"}))
        return await self.reply(f"h{self._n}")

    async def call(self, action: str, **fields) -> dict:
        self._n += 1
        request_id = f"r{self._n}"
        await self.ws.send(json.dumps({"id": request_id, "action": action, **fields}))
        return await self.reply(request_id)


# ----------------------------------------------------------------------------- config
def test_config_rejects_non_loopback_and_persists_token(tmp_path):
    cfg = BridgeConfig(host="0.0.0.0", port=17613, data_dir=tmp_path)
    with pytest.raises(ValueError, match="127.0.0.1"):
        cfg.validate()

    cfg = BridgeConfig(host="127.0.0.1", port=17613, data_dir=tmp_path)
    token = cfg.ensure_token()
    assert len(token) == 64 and token == cfg.token_file.read_text(encoding="utf-8").strip()
    again = BridgeConfig(host="127.0.0.1", port=17613, data_dir=tmp_path)
    assert again.ensure_token() == token, "the pairing token must persist across restarts"
    assert cfg.uri == "ws://127.0.0.1:17613"


def test_load_config_reads_env(tmp_path, monkeypatch):
    monkeypatch.setenv("OMNIBRIDGE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OMNIBRIDGE_BRIDGE_PORT", "17999")
    monkeypatch.setenv("OMNIBRIDGE_BRIDGE_PERMISSION_LEVEL", "2")
    monkeypatch.setenv("ROBLOX_STUDIO_MCP_COMMAND", "/usr/bin/true")
    monkeypatch.setenv("ROBLOX_STUDIO_MCP_ARGS", "--flag value")
    cfg = load_config()
    assert cfg.port == 17999 and cfg.permission_level == 2
    assert cfg.studio_command == "/usr/bin/true" and cfg.studio_args == ["--flag", "value"]
    assert cfg.data_dir == tmp_path.resolve()


# ----------------------------------------------------------------------------- security
def test_origin_policy_rejects_web_pages():
    prefixes = ("chrome-extension://", "moz-extension://")
    ok, _ = origin_allowed("chrome-extension://abcdefghijklmnop", prefixes)
    assert ok
    ok, _ = origin_allowed("moz-extension://1234-abcd", prefixes)
    assert ok
    for bad in ("https://evil.example", "http://127.0.0.1:8765", "null", "file://"):
        ok, reason = origin_allowed(bad, prefixes)
        assert not ok and "extension" in reason
    ok, _ = origin_allowed(None, prefixes)  # native client without Origin header
    assert ok


def test_token_compare_and_redaction():
    assert check_token("abc", "abc") and not check_token("abc", "abd")
    assert not check_token("", "") and not check_token("abc", "")
    text = redact("api_key=sk-1234567890abcdefghijklmn and token: ghp_abcdefghijklmnopqrstuvwx")
    assert "sk-123" not in text and "ghp_" not in text and "[REDACTED]" in text


def test_argument_validation_uses_published_schema():
    schema = {"type": "object",
              "properties": {"code": {"type": "string"}, "count": {"type": "integer"},
                             "mode": {"type": "string", "enum": ["a", "b"]}},
              "required": ["code"], "additionalProperties": False}
    assert validate_arguments(schema, {"code": "print(1)", "count": "3"})["count"] == 3
    with pytest.raises(ArgumentError, match="missing required"):
        validate_arguments(schema, {})
    with pytest.raises(ArgumentError, match="must be integer"):
        validate_arguments(schema, {"code": "x", "count": "many"})
    with pytest.raises(ArgumentError, match="unknown argument"):
        validate_arguments(schema, {"code": "x", "nope": 1})
    with pytest.raises(ArgumentError, match="one of"):
        validate_arguments(schema, {"code": "x", "mode": "z"})
    assert validate_arguments(None, {"anything": 1}) == {"anything": 1}


def test_permission_levels_and_rate_limiter(tmp_path):
    assert classify_tool_level("run_code", "") == 4
    assert classify_tool_level("create_object", "") == 3
    assert classify_tool_level("get_studio_state", "") == 1
    assert classify_tool_level("mystery_tool", "") == 2
    limiter = RateLimiter(max_per_minute=3)
    assert [limiter.allow() for _ in range(3)] == [True, True, True]
    assert limiter.allow() is False
    audit = AuditLog(tmp_path / "audit.jsonl")
    audit.write("probe", foo="bar")
    assert audit.tail(1)[0]["event"] == "probe"


# ----------------------------------------------------------------------------- registry
def test_registry_is_dynamic_not_hardcoded():
    registry = Registry()
    registry.refresh([ToolInfo("list_roblox_studios", "List studios",
                               {"type": "object", "properties": {}}),
                      ToolInfo("create_part", "Create a part",
                               {"type": "object",
                                "properties": {"name": {"type": "string"}},
                                "required": ["name"]})])
    assert registry.names() == ["create_part", "list_roblox_studios"]
    assert registry.level_of("create_part") == 3 and registry.level_of("list_roblox_studios") == 1
    prompt = registry.prompt_block()
    assert "create_part(name)" in prompt
    # an empty server yields an empty registry: nothing is invented
    registry.refresh([])
    assert len(registry) == 0 and registry.prompt_block() == ""


# ----------------------------------------------------------------------------- process
def test_process_discovery_prefers_explicit_command(monkeypatch):
    monkeypatch.delenv("OMNIBRIDGE_STUDIO_MCP_COMMAND", raising=False)
    monkeypatch.delenv("ROBLOX_STUDIO_MCP_COMMAND", raising=False)
    spec = discover_launch_spec("/custom/StudioMCP", ["--port", "0"])
    assert spec.command == "/custom/StudioMCP" and spec.args == ["--port", "0"]
    spec = discover_launch_spec()
    assert spec.source in ("discovered", "missing")
    if spec.source == "missing":
        assert spec.command == ""


# ----------------------------------------------------------------------------- MCP client
def test_mcp_client_discovery_timeout_and_restart(tmp_path):
    async def scenario():
        cfg = make_config(tmp_path)
        client = StudioMCPClient(cfg)
        try:
            tools = await client.discover()
            assert [t.name for t in tools] == ["list_roblox_studios", "get_studio_state",
                                               "run_code", "slow_tool"]
            assert client.server_info["name"] == "fake-studio-mcp"
            result = await client.call_tool("get_studio_state", {"studio_id": "abc"})
            assert not result["isError"] and "abc" in result["text"]
            with pytest.raises(MCPFailure) as info:
                await client.call_tool("slow_tool", {"seconds": 1.5}, timeout=0.3)
            assert info.value.code == "timeout"
            assert client.connected, "a timeout must not kill the session"
            recovered = await client.call_tool("get_studio_state", {}, timeout=6.0)
            assert "TestPlace" in recovered["text"]
            await client.restart()
            assert client.connected and len(client.tools) == 4
        finally:
            await client.stop()
        assert client.connected is False

    asyncio.run(scenario())


def test_mcp_client_retries_empty_tool_list(tmp_path):
    async def scenario():
        cfg = make_config(tmp_path, studio_args=["-m", FIXTURE, "--empty-first"])
        client = StudioMCPClient(cfg)
        try:
            tools = await client.discover()
            assert len(tools) == 4, "empty tools/list must be retried, not treated as failure"
            assert client.discovery_attempts_used == 2
        finally:
            await client.stop()

    asyncio.run(scenario())


def test_connector_reports_no_tools_state_without_inventing(tmp_path):
    async def scenario():
        cfg = make_config(tmp_path, studio_args=["-m", FIXTURE, "--no-tools"],
                          discovery_attempts=2, discovery_backoff_s=0.05)
        client = StudioMCPClient(cfg)
        connector = RobloxConnector(client)
        try:
            state = await connector.connect()
            assert state == STATE_NO_TOOLS
            status = connector.status()
            assert status["toolCount"] == 0 and status["hint"]
            assert "never" in status["hint"].lower() or "refuses" in status["hint"].lower()
        finally:
            await client.stop()

    asyncio.run(scenario())


def test_connector_reports_studio_closed_when_server_missing(tmp_path):
    async def scenario():
        cfg = make_config(tmp_path, studio_command="/nonexistent/StudioMCP", studio_args=[],
                          discovery_attempts=1)
        client = StudioMCPClient(cfg)
        connector = RobloxConnector(client)
        try:
            state = await connector.connect()
            assert state == STATE_STUDIO_CLOSED
            assert "Studio" in connector.status()["hint"]
        finally:
            await client.stop()

    asyncio.run(scenario())


# ----------------------------------------------------------------------------- manager
def test_connection_manager_validates_and_audits(tmp_path):
    async def scenario():
        cfg = make_config(tmp_path, permission_level=3)
        client = StudioMCPClient(cfg)
        registry = Registry()
        connector = RobloxConnector(client)
        audit = AuditLog(cfg.audit_file)
        manager = ConnectionManager(cfg, client, registry, connector, audit)
        try:
            tools = await manager.list_tools(refresh=True)
            assert {t["name"] for t in tools} == {"list_roblox_studios", "get_studio_state",
                                                  "run_code", "slow_tool"}
            with pytest.raises(BridgeError) as info:
                await manager.call_tool("does_not_exist", {})
            assert info.value.code == "unknown_tool"
            with pytest.raises(BridgeError) as info:
                await manager.call_tool("run_code", {"code": "print(1)"})
            assert info.value.code == "permission_denied" and "level 4" in info.value.message
            with pytest.raises(BridgeError) as info:
                await manager.call_tool("run_code", {})
            assert info.value.code == "permission_denied"  # still gated before arguments
            result = await manager.call_tool("get_studio_state", {"studio_id": "s1"})
            assert result["tool"] == "get_studio_state" and not result["isError"]
            assert manager.stats["ok"] >= 1 and manager.stats["errors"] >= 2
            events = [entry["event"] for entry in audit.tail(20)]
            assert "tool_rejected" in events and "tool_call" in events
            assert "tool_result" in events
        finally:
            await client.stop()

    asyncio.run(scenario())


def test_connection_manager_argument_errors_when_level_allows(tmp_path):
    async def scenario():
        cfg = make_config(tmp_path, permission_level=4)
        client = StudioMCPClient(cfg)
        manager = ConnectionManager(cfg, client, Registry(), RobloxConnector(client))
        try:
            await manager.list_tools(refresh=True)
            with pytest.raises(BridgeError) as info:
                await manager.call_tool("run_code", {})
            assert info.value.code == "invalid_arguments"
            with pytest.raises(BridgeError) as info:
                await manager.call_tool("run_code", {"code": "x", "extra": 1})
            assert info.value.code == "invalid_arguments"
            ok = await manager.call_tool("run_code", {"code": "print('hi')"})
            assert "print('hi')" in ok["text"]
        finally:
            await client.stop()

    asyncio.run(scenario())


def test_manager_returns_not_connected_without_mcp(tmp_path):
    async def scenario():
        cfg = make_config(tmp_path, studio_command="/nonexistent/StudioMCP", studio_args=[],
                          discovery_attempts=1)
        client = StudioMCPClient(cfg)
        manager = ConnectionManager(cfg, client, Registry(), RobloxConnector(client))
        with pytest.raises(BridgeError) as info:
            await manager.call_tool("anything", {})
        assert info.value.code == "unknown_tool"  # nothing discovered ⇒ nothing callable

    asyncio.run(scenario())


# ----------------------------------------------------------------------------- websocket
def test_websocket_end_to_end(tmp_path):
    async def scenario():
        from websockets.asyncio.client import connect
        from websockets.exceptions import ConnectionClosed, InvalidStatus

        cfg = make_config(tmp_path)
        state = await stack(cfg)
        _client, _registry, _connector, manager, _server, _audit = state
        uri = f"ws://127.0.0.1:{cfg.port}/"
        try:
            # 1. a plain web origin is refused during the HTTP upgrade
            with pytest.raises(InvalidStatus) as info:
                async with connect(uri, origin="https://evil.example", open_timeout=5):
                    pass
            assert info.value.response.status_code == 403

            # 2. a missing/wrong token is refused after hello
            async with connect(uri, origin="chrome-extension://abcdefgh", open_timeout=5) as ws:
                client = WSClient(ws)
                reply = await client.hello("wrong-token")
                assert reply["ok"] is False and reply["error"]["code"] == "unauthorized"
                with pytest.raises(ConnectionClosed):
                    await ws.recv()

            # 3. correct token → full session
            async with connect(uri, origin="chrome-extension://abcdefgh", open_timeout=5) as ws:
                client = WSClient(ws)
                reply = await client.hello(cfg.token)
                assert reply["type"] == "hello_ok" and reply["protocol"] == 1
                assert reply["bridge"]["state"] in ("studio_closed", "ready", "no_tools",
                                                    "mcp_disabled", "mcp_unreachable",
                                                    "studio_open_no_project")

                pong = await client.call("ping")
                assert pong["ok"] and pong["result"]["pong"] is True

                listed = await client.call("list_tools", refresh=True)
                names = [tool["name"] for tool in listed["result"]["tools"]]
                assert "get_studio_state" in names

                called = await client.call("call_tool", tool="get_studio_state",
                                           arguments={"studio_id": "ws1"})
                assert called["ok"] and "ws1" in called["result"]["text"]

                denied = await client.call("call_tool", tool="nope", arguments={})
                assert denied["ok"] is False and denied["error"]["code"] == "unknown_tool"

                bad_args = await client.call("call_tool", tool="run_code",
                                             arguments={"unexpected": True})
                assert bad_args["ok"] is False
                assert bad_args["error"]["code"] in ("permission_denied", "invalid_arguments")

                unknown = await client.call("delete_everything")
                assert unknown["ok"] is False and unknown["error"]["code"] == "unknown_action"

                status = await client.call("status")
                assert status["ok"] and status["result"]["bridge"] == "studio_bridge"
                assert status["result"]["toolCount"] >= 4

                prompt = await client.call("tools_prompt")
                assert prompt["ok"] and "get_studio_state" in prompt["result"]["prompt"]

                stopped = await client.call("stop_task", task="never-existed")
                assert stopped["ok"] and stopped["result"]["cancelled"] is False

                tail = await client.call("audit_tail", limit=5)
                assert tail["ok"] and isinstance(tail["result"]["entries"], list)
                assert manager.stats["calls"] >= 2

            # 4. malformed frames never crash the server
            async with connect(uri, origin="chrome-extension://abcdefgh", open_timeout=5) as ws:
                client = WSClient(ws)
                assert (await client.hello(cfg.token))["type"] == "hello_ok"
                await ws.send("not json at all")
                reply = await client.reply()
                assert reply["ok"] is False and reply["error"]["code"] == "bad_request"
                await ws.send(json.dumps([1, 2, 3]))
                reply = await client.reply()
                assert reply["ok"] is False
                # the bridge also pushes state events to connected extensions
                assert any(frame["event"] == "mcp_state" for frame in client.events)
        finally:
            await close(state)

    asyncio.run(scenario())


def test_websocket_rejects_unknown_path(tmp_path):
    async def scenario():
        from websockets.asyncio.client import connect
        from websockets.exceptions import InvalidStatus

        cfg = make_config(tmp_path)
        state = await stack(cfg)
        try:
            with pytest.raises(InvalidStatus) as info:
                async with connect(f"ws://127.0.0.1:{cfg.port}/admin",
                                   origin="chrome-extension://abc", open_timeout=5):
                    pass
            assert info.value.response.status_code == 404
        finally:
            await close(state)

    asyncio.run(scenario())


def test_handshake_timeout_closes_silent_clients(tmp_path):
    async def scenario():
        from websockets.asyncio.client import connect
        from websockets.exceptions import ConnectionClosed

        cfg = make_config(tmp_path, auth_timeout_s=0.4)
        state = await stack(cfg)
        try:
            async with connect(f"ws://127.0.0.1:{cfg.port}/", origin="chrome-extension://abc",
                               open_timeout=5) as ws:
                first = json.loads(await asyncio.wait_for(ws.recv(), 5))
                assert first["type"] == "error" and first["error"]["code"] == "bad_request"
                with pytest.raises(ConnectionClosed) as info:
                    await ws.recv()
                assert info.value.rcvd.code == 4003
        finally:
            await close(state)

    asyncio.run(scenario())


# ----------------------------------------------------------------------------- setup page
def test_setup_page_and_status_json(tmp_path):
    async def scenario():
        import httpx

        cfg = make_config(tmp_path)
        state = await stack(cfg)
        _client, _registry, _connector, _manager, _server, _audit = state
        base = f"http://127.0.0.1:{cfg.port}"
        try:
            async with httpx.AsyncClient(timeout=10) as http:
                # typed in the address bar (no Origin, Sec-Fetch-Site: none) → token visible
                page = await http.get(f"{base}/", headers={"Sec-Fetch-Site": "none",
                                                           "Sec-Fetch-Mode": "navigate"})
                assert page.status_code == 200
                assert "Pont OMNIBRIDGE" in page.text
                assert cfg.token in page.text
                assert "Content-Security-Policy" in page.headers
                assert page.headers["X-Frame-Options"] == "DENY"

                # requested by another origin (extension, page) → token hidden
                hidden = await http.get(f"{base}/",
                                        headers={"Origin": "chrome-extension://abcdefgh",
                                                 "Sec-Fetch-Mode": "cors"})
                assert hidden.status_code == 200 and cfg.token not in hidden.text

                status = await http.get(f"{base}/status.json",
                                        headers={"Origin": "chrome-extension://abcdefgh"})
                assert status.status_code == 200
                payload = status.json()
                assert payload["ok"] is True and "state" in payload
                assert cfg.token not in status.text
                assert "Access-Control-Allow-Origin" not in status.headers

                health = await http.get(f"{base}/health")
                assert health.status_code == 200 and health.json()["protocol"] == 1

                missing = await http.get(f"{base}/admin")
                assert missing.status_code == 404

                refreshed = await http.get(f"{base}/?refresh=1",
                                           headers={"Sec-Fetch-Site": "none"})
                assert refreshed.status_code == 200
        finally:
            await close(state)

    asyncio.run(scenario())


def test_token_reveal_policy():
    from omnibridge.studio_bridge.status_page import human_state, should_reveal_token

    assert should_reveal_token(None, "navigate", "none") is True
    assert should_reveal_token(None, None, None) is True
    assert should_reveal_token("chrome-extension://abc", "cors", "none") is False
    assert should_reveal_token(None, "cors", "none") is False
    assert should_reveal_token(None, "navigate", "cross-site") is False
    for state in ("ready", "no_tools", "studio_closed"):
        title, hint, level = human_state(state)
        assert title and hint and level in ("ok", "warn", "error")


# ----------------------------------------------------------------------------- CLI
def test_cli_check_and_print_token(tmp_path):
    env = {**os.environ, "OMNIBRIDGE_DATA_DIR": str(tmp_path),
           "OMNIBRIDGE_BRIDGE_PORT": "17613"}
    env.pop("ROBLOX_STUDIO_MCP_COMMAND", None)
    token = os.popen  # noqa: F841 - keeps flake quiet, not used
    out = __import__("subprocess").run([sys.executable, "-m", "python_bridge", "--print-token"],
                                       capture_output=True, text=True, env=env, cwd=ROOT)
    assert out.returncode == 0, out.stderr
    printed = out.stdout.strip()
    assert len(printed) == 64

    check = __import__("subprocess").run([sys.executable, "-m", "python_bridge", "--check"],
                                          capture_output=True, text=True, env=env, cwd=ROOT)
    assert check.returncode == 0, check.stderr
    payload = json.loads(check.stdout)
    assert payload["uri"] == "ws://127.0.0.1:17613"
    assert payload["host"] == "127.0.0.1"
    assert payload["state"]["state"] in ("studio_closed", "missing")
    assert payload["permissionLevel"] in (1, 2, 3, 4)


def test_windows_batch_launch_uses_cmd_and_the_roblox_folder(tmp_path, monkeypatch):
    """Studio's settings: cmd.exe /c cd /d %LOCALAPPDATA%\\Roblox && .\\mcp.bat"""
    fake = tmp_path / "Roblox" / "mcp.bat"
    fake.parent.mkdir(parents=True)
    fake.write_text("@echo off\n", encoding="utf-8")

    spec = discover_launch_spec(str(fake), [])
    if __import__("platform").system() == "Windows":
        assert spec.command == "cmd.exe" and spec.args == ["/c", "mcp.bat"]
        assert spec.cwd == str(fake.parent)
    else:
        assert spec.command == str(fake)

    from omnibridge.studio_bridge.process_manager import LaunchSpec

    spec = LaunchSpec("cmd.exe", ["/c", "mcp.bat"], "discovered", cwd=str(fake.parent))
    assert spec.cwd == str(fake.parent) and spec.display == "cmd.exe /c mcp.bat"
