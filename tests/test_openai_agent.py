"""OpenAI-compatible function-calling loop, exercised with a fake provider (httpx MockTransport)."""
from __future__ import annotations

import json

import httpx
import pytest

from omnibridge.openai_agent import AgentConfig, OpenAIToolAgent


def make_agent(bridge, handler, **cfg) -> OpenAIToolAgent:
    client = httpx.AsyncClient(base_url="https://fake.local/v1",
                               transport=httpx.MockTransport(handler))
    config = AgentConfig(provider="deepseek", api_key="test-key", model="deepseek-chat", **cfg).resolve()
    return OpenAIToolAgent(bridge, config, client=client)


def test_agent_executes_tool_then_answers(bridge, run):
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        seen.append(payload)
        assert request.headers["authorization"] == "Bearer test-key"
        if len(seen) == 1:
            return httpx.Response(200, json={"choices": [{"message": {
                "role": "assistant", "content": None,
                "tool_calls": [{"id": "call_1", "type": "function",
                                "function": {"name": "knowledge_stats", "arguments": "{}"}}],
            }, "finish_reason": "tool_calls"}]})
        return httpx.Response(200, json={"choices": [{"message": {
            "role": "assistant", "content": "Le serveur connaît 3 chunks."},
            "finish_reason": "stop"}]})

    events: list[dict] = []
    agent = make_agent(bridge, handler)
    result = run(agent.run("Combien de chunks ?", on_event=events.append))

    assert result["ok"] is True
    assert "chunks" in result["final"]
    assert result["toolCalls"] == [{"step": 1, "tool": "knowledge_stats", "ok": True}]
    assert events and events[0]["tool"] == "knowledge_stats"
    # second request must carry the tool result back to the model
    tool_messages = [m for m in seen[1]["messages"] if m["role"] == "tool"]
    assert tool_messages and '"chunks"' in tool_messages[0]["content"]
    assert seen[0]["tools"][0]["type"] == "function"
    assert len(seen[0]["tools"]) == bridge.registry.size


def test_agent_reports_tool_errors_to_the_model(bridge, run):
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        seen.append(payload)
        if len(seen) == 1:
            return httpx.Response(200, json={"choices": [{"message": {
                "role": "assistant", "content": None,
                "tool_calls": [{"id": "c1", "type": "function",
                                "function": {"name": "file_read", "arguments": "{\"path\": \"../etc/passwd\"}"}}],
            }}]})
        return httpx.Response(200, json={"choices": [{"message": {
            "role": "assistant", "content": "Accès refusé, je corrige."}}]})

    result = run(make_agent(bridge, handler).run("lis /etc/passwd"))
    tool_msg = [m for m in seen[1]["messages"] if m["role"] == "tool"][0]
    assert '"ok": false' in tool_msg["content"]
    assert result["ok"] is True


def test_agent_stops_at_max_steps(bridge, run):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {
            "role": "assistant", "content": None,
            "tool_calls": [{"id": "loop", "type": "function",
                            "function": {"name": "system_health", "arguments": "{}"}}]}}]})

    result = run(make_agent(bridge, handler, max_steps=2).run("boucle"))
    assert result["ok"] is False
    assert "2 steps" in result["error"]
    assert len(result["toolCalls"]) == 2


def test_agent_without_key_reports_honestly(bridge, run):
    config = AgentConfig(provider="openai", api_key="").resolve()
    agent = OpenAIToolAgent(bridge, config, client=httpx.AsyncClient(
        base_url="https://fake.local/v1", transport=httpx.MockTransport(lambda r: httpx.Response(500))))
    result = run(agent.run("test"))
    assert result["ok"] is False
    assert "Missing API key" in result["error"]


def test_agent_provider_errors_are_surfaced(bridge, run):
    agent = make_agent(bridge, lambda r: httpx.Response(401, text="invalid api key"))
    with pytest.raises(RuntimeError, match="401"):
        run(agent.run("test"))


def test_provider_table_matches_documented_env_vars():
    from omnibridge.openai_agent import PROVIDERS

    assert PROVIDERS["deepseek"][1] == "DEEPSEEK_API_KEY"
    assert PROVIDERS["openai"][1] == "OPENAI_API_KEY"
    assert PROVIDERS["ollama"][1] == ""  # local, no key
    # every named provider except `custom` ships a real base URL
    assert all(v[0].startswith("http") for k, v in PROVIDERS.items() if k != "custom")
    assert PROVIDERS["custom"][0] == ""  # requires --base-url
    assert PROVIDERS["gemini"][1] == "GEMINI_API_KEY"
    assert PROVIDERS["xai"][1] == "XAI_API_KEY"
    assert PROVIDERS["ollama"][0].startswith("http://127.0.0.1")
