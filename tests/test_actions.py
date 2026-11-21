"""OpenAPI actions (ChatGPT Custom GPT Actions, Copilot Studio) + provider table."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from omnibridge.http_api import create_http_app
from omnibridge.openapi_actions import build_actions_openapi


@pytest.fixture
def client(bridge, cfg):
    app = create_http_app(bridge, cfg)
    with TestClient(app) as c:
        yield c


def auth(cfg) -> dict[str, str]:
    return {"Authorization": f"Bearer {cfg.token}"}


def test_openapi_document_is_public_and_complete(client, bridge):
    doc = client.get("/openapi/actions.json")
    assert doc.status_code == 200
    spec = doc.json()
    assert spec["openapi"].startswith("3.1")
    assert spec["components"]["securitySchemes"]["bearerAuth"]["scheme"] == "bearer"
    assert len(spec["paths"]) == bridge.registry.size
    assert "/api/actions/file_read" in spec["paths"]


def test_openapi_operations_have_typed_bodies(client):
    spec = client.get("/openapi/actions.json").json()
    op = spec["paths"]["/api/actions/file_read"]["post"]
    assert op["operationId"] == "file_read"
    schema = op["requestBody"]["content"]["application/json"]["schema"]
    assert schema["properties"]["path"]["type"] == "string"
    assert schema["required"] == ["path"]
    assert op["security"] == [{"bearerAuth": []}]
    assert len(op["description"]) <= 800

    sensitive = spec["paths"]["/api/actions/process_run"]["post"]
    body = sensitive["requestBody"]["content"]["application/json"]["schema"]
    assert "confirm" in body["properties"]
    assert "SENSITIVE" in sensitive["description"]


def test_openapi_uses_public_url_override(bridge):
    bridge.cfg.public_url = "https://demo.example.com"
    spec = build_actions_openapi(bridge, bridge.cfg.public_url)
    assert spec["servers"][0]["url"] == "https://demo.example.com"


def test_action_executes_real_tool(client, cfg):
    r = client.post("/api/actions/file_list", headers=auth(cfg), json={"path": "."})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["tool"] == "file_list"
    assert body["result"]["count"] >= 1


def test_action_requires_token(client):
    assert client.post("/api/actions/system_health", json={}).status_code == 401


def test_action_unknown_tool_is_404(client, cfg):
    r = client.post("/api/actions/ghost_tool", headers=auth(cfg), json={})
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "unknown_tool"


def test_action_permission_and_confirm(client, cfg):
    denied = client.post("/api/actions/process_run", headers=auth(cfg), json={"action": "python_version"})
    assert denied.status_code == 403
    ok = client.post("/api/actions/process_run", headers=auth(cfg),
                     json={"action": "python_version", "confirm": True})
    assert ok.status_code == 200 and ok.json()["result"]["passed"] is True


def test_action_validation_error(client, cfg):
    r = client.post("/api/actions/file_read", headers=auth(cfg), json={})
    assert r.status_code == 400


def test_providers_include_web_ai_vendors(client, cfg):
    providers = {p["name"]: p for p in client.get("/api/webai/providers", headers=auth(cfg)).json()["providers"]}
    for name in ("gemini", "xai", "deepseek", "openai", "ollama", "openrouter", "mistral", "groq"):
        assert name in providers, name
    assert providers["gemini"]["baseUrl"].startswith("https://generativelanguage.googleapis.com")
    assert providers["gemini"]["apiKeyEnv"] == "GEMINI_API_KEY"
    assert providers["xai"]["baseUrl"] == "https://api.x.ai/v1"
    assert providers["ollama"]["needsKey"] is False


def test_browser_last_message_tool_registered(bridge):
    tool = bridge.registry.get("browser_get_last_assistant_message")
    assert tool is not None and tool.level == 1


def test_extension_adapters_declare_all_five_sites():
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    src = (root / "extension" / "site-adapters.js").read_text()
    for host in ("chatgpt\\.com", "chat\\.deepseek\\.com", "gemini\\.google\\.com",
                 "copilot\\.microsoft\\.com", "grok\\.com"):
        assert host in src, host
    manifest = json.loads((root / "extension" / "manifest.json").read_text())
    matches = [m for s in manifest["content_scripts"] for m in s["matches"]]
    for expected in ("https://chat.deepseek.com/*", "https://gemini.google.com/*",
                     "https://copilot.microsoft.com/*", "https://grok.com/*", "https://chatgpt.com/*"):
        assert expected in matches
    assert "clipboardWrite" in manifest["permissions"]
