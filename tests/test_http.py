"""HTTP API: auth, REST endpoints, bridge endpoints, MCP mount."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from omnibridge.http_api import create_http_app


@pytest.fixture
def client(bridge, cfg):
    app = create_http_app(bridge, cfg)
    with TestClient(app) as c:
        yield c


def auth(cfg) -> dict[str, str]:
    return {"Authorization": f"Bearer {cfg.token}"}


def test_health_is_public(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_api_requires_token(client):
    assert client.get("/api/tools").status_code == 401
    assert client.post("/api/tools/call", json={"name": "system_health"}).status_code == 401


def test_api_accepts_bearer_and_header(client, cfg):
    assert client.get("/api/tools", headers=auth(cfg)).status_code == 200
    assert client.get("/api/tools", headers={"X-Omnibridge-Token": cfg.token}).status_code == 200
    assert client.get(f"/api/tools?token={cfg.token}").status_code == 200


def test_tools_and_call(client, cfg, bridge):
    tools = client.get("/api/tools", headers=auth(cfg)).json()
    assert tools["count"] == bridge.registry.size
    filtered = client.get("/api/tools?category=roblox", headers=auth(cfg)).json()
    assert all(t["category"] == "roblox" for t in filtered["tools"])

    ok = client.post("/api/tools/call", headers=auth(cfg),
                     json={"name": "file_list", "args": {"path": "."}}).json()
    assert ok["ok"] is True and ok["result"]["count"] >= 1

    denied = client.post("/api/tools/call", headers=auth(cfg),
                         json={"name": "process_run", "args": {"action": "python_version"}})
    assert denied.status_code == 403

    bad = client.post("/api/tools/call", headers=auth(cfg), json={"name": "file_read", "args": {}})
    assert bad.status_code == 400


def test_knowledge_endpoints(client, cfg):
    idx = client.post("/api/knowledge/index", headers=auth(cfg), json={
        "source": "test", "title": "Test doc", "text": "Remote events must validate arguments."})
    assert idx.status_code == 200
    hits = client.post("/api/knowledge/retrieve", headers=auth(cfg),
                       json={"query": "validate arguments", "limit": 3}).json()
    assert hits["hits"]
    assert client.get("/api/knowledge/stats", headers=auth(cfg)).json()["sources"] >= 1


def test_tasks_endpoint(client, cfg):
    started = client.post("/api/tools/call", headers=auth(cfg),
                          json={"name": "agent_start_task", "args": {"goal": "inspect project"}}).json()
    task_id = started["result"]["taskId"]
    listing = client.get("/api/tasks", headers=auth(cfg)).json()
    assert any(t["id"] == task_id for t in listing["tasks"])


def test_bridge_registration_and_poll(client, cfg):
    reg = client.post("/bridge/register", headers=auth(cfg),
                      json={"clientId": "client-1", "info": {"mode": "manual"}})
    assert reg.status_code == 200 and reg.json()["ok"] is True
    status = client.get("/bridge/status", headers=auth(cfg)).json()
    assert status["connected"] is True
    assert status["clients"][0]["clientId"] == "client-1"
    # unknown request ids are rejected honestly
    res = client.post("/bridge/result", headers=auth(cfg),
                      json={"requestId": "does-not-exist", "ok": True, "data": {}})
    assert res.status_code == 404


def test_dashboard_and_info(client, cfg):
    assert client.get("/").status_code == 200
    info = client.get("/api/info", headers=auth(cfg)).json()
    assert info["python"] is True
    assert info["permissionLevel"] == cfg.permission_level


def test_mcp_endpoint_requires_token(client):
    payload = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
               "params": {"protocolVersion": "2025-11-25", "capabilities": {},
                          "clientInfo": {"name": "test", "version": "0"}}}
    headers = {"Accept": "application/json, text/event-stream"}
    assert client.post("/mcp", json=payload, headers=headers).status_code == 401
    ok = client.post("/mcp", json=payload, headers={**headers, "Authorization": "Bearer " + "x" * 10})
    assert ok.status_code == 401  # wrong token
