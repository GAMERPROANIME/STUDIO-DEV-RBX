"""Guided setup page (`GET /demarrer`) for the in-page panel — option A.

Proofs:
  * the page is public (no token needed to read it), renders the 4 French steps;
  * the pairing code is only shown to a request typed in the address bar;
  * it never leaks the code to an extension/page origin, and disables framing, caching, CORS;
  * the page reports the real Studio state (studio closed in CI, honestly labelled);
  * Windows `.bat` launch is wrapped in cmd.exe / c so the Studio MCP can actually start.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from omnibridge.http_api import create_http_app
from omnibridge.roblox.connector import _wrap_windows_batch
from omnibridge.setup_page import build_setup_page, should_reveal_token


@pytest.fixture
def client(bridge, cfg):
    app = create_http_app(bridge, cfg)
    with TestClient(app) as test_client:
        yield test_client


def test_setup_page_is_public_and_has_the_four_steps(client, cfg):
    response = client.get("/demarrer", headers={"Sec-Fetch-Site": "none",
                                               "Sec-Fetch-Mode": "navigate"})
    assert response.status_code == 200
    body = response.text
    for needle in ("Installer l'extension", "chrome://extensions", "Mode développeur",
                   "Lire la réponse", "Exécuter", "MCP Servers", "chat.deepseek.com"):
        assert needle in body, needle
    assert cfg.token in body  # typed in the address bar → the code is shown
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "Content-Security-Policy" in response.headers
    assert response.headers["Cache-Control"] == "no-store"
    # the page must never be reachable cross-origin with a readable body
    assert "Access-Control-Allow-Origin" not in response.headers


def test_setup_page_hides_the_code_from_other_origins(client, cfg):
    for headers in ({"Origin": "chrome-extension://abcdefgh", "Sec-Fetch-Mode": "cors"},
                    {"Origin": "https://evil.example"},
                    {"Sec-Fetch-Mode": "cors", "Sec-Fetch-Site": "none"},
                    {"Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "navigate"}):
        response = client.get("/demarrer", headers=headers)
        assert response.status_code == 200
        assert cfg.token not in response.text, headers
        assert "barre d'adresse" in response.text


def test_setup_page_reports_studio_state(client):
    import json

    response = client.get("/demarrer", headers={"Sec-Fetch-Site": "none"})
    assert "Studio" in response.text
    # the technical block is valid JSON and tells whether Studio was reachable
    start = response.text.index("<pre>") + len("<pre>")
    end = response.text.index("</pre>")
    import html as html_module

    payload = json.loads(html_module.unescape(response.text[start:end]))
    assert payload["studioState"] in ("ready", "studio_closed", "mcp_unreachable")
    assert payload["tokenShown"] is True


def test_reveal_policy_is_shared_with_the_studio_bridge():
    assert should_reveal_token(None, "navigate", "none") is True
    assert should_reveal_token("chrome-extension://abc", "cors", "none") is False
    assert should_reveal_token(None, "no-cors", "none") is False
    assert should_reveal_token(None, "navigate", "same-origin") is False


def test_build_setup_page_without_token():
    page = build_setup_page(server_url="http://127.0.0.1:8765", token="secret-token",
                            studio_state="ready", studio_detail="", tool_count=12,
                            reveal=False)
    assert "secret-token" not in page
    assert "barre d'adresse" in page
    assert '"ready"' in page or "&quot;ready&quot;" in page


def test_windows_batch_is_wrapped_and_runs_in_its_folder():
    """Studio's own settings say: cmd.exe /c cd /d %LOCALAPPDATA%\Roblox && .\mcp.bat"""
    # POSIX-style literal so the assertion is meaningful on every OS (backslashes are not
    # separators on Linux); the logic under test is the .bat + cwd wrapping.
    command, args, cwd, _source = _wrap_windows_batch(
        "/home/me/AppData/Local/Roblox/mcp.bat", [], system="Windows")
    assert command == "cmd.exe"
    assert args == ["/c", "mcp.bat"]
    assert cwd == "/home/me/AppData/Local/Roblox"
    command, args, cwd, _source = _wrap_windows_batch("/usr/local/bin/StudioMCP", ["--x"],
                                                      system="Linux")
    assert command == "/usr/local/bin/StudioMCP" and args == ["--x"] and cwd is None


def test_panel_endpoints_used_by_the_extension(client, cfg):
    """Exactly what extension/bridge-panel.js calls: prompt, run, health."""
    auth = {"Authorization": f"Bearer {cfg.token}"}
    health = client.get("/api/health")
    assert health.status_code == 200 and health.json()["ok"] is True

    prompt = client.get("/api/webai/prompt?budgetChars=3000", headers=auth)
    assert prompt.status_code == 200
    assert prompt.json()["chars"] > 0 and prompt.json()["tools"]

    reply = ('```json\n{"calls": [{"tool": "system_health", "args": {}}]}\n```')
    run = client.post("/api/webai/run", headers=auth, json={"reply": reply})
    assert run.status_code == 200
    payload = run.json()
    assert payload["ok"] is True and payload["executed"] == 1
    assert "OMNIBRIDGE RESULTS" in payload["block"]

    # a malformed reply never executes anything
    bad = client.post("/api/webai/run", headers=auth, json={"reply": "just chatting"})
    assert bad.status_code == 200 and bad.json()["ok"] is False
    assert bad.json()["executed"] == 0
