"""Prompt bridge + OpenAI tool export: parsing, budgets, execution, remote checks."""
from __future__ import annotations

import json

import pytest

from omnibridge.core.permissions import PermissionDenied
from omnibridge.webai import build_prompt, check_remote_mcp, openai_tools, parse_calls, run_calls


def test_prompt_contains_protocol_and_real_tools(bridge):
    prompt = build_prompt(bridge, 8000)
    assert "omnibridge" not in prompt["prompt"].lower() or "OMNIBRIDGE" in prompt["prompt"]
    assert "calls" in prompt["prompt"]
    assert "system_health" in prompt["tools"]
    assert prompt["chars"] <= 8000 + 400  # small footer tolerance
    for name in prompt["tools"]:
        assert bridge.registry.get(name) is not None


def test_prompt_respects_tiny_budget(bridge):
    small = build_prompt(bridge, 2000)
    assert small["toolsOmitted"] > 0
    assert len(small["tools"]) < bridge.registry.size
    # the essentials come first
    assert small["tools"][0] == "system_health"


def test_prompt_category_filter(bridge):
    prompt = build_prompt(bridge, 9000, ["roblox"])
    assert prompt["tools"]
    assert all(bridge.registry.get(t).category == "roblox" for t in prompt["tools"])


@pytest.mark.parametrize("reply", [
    '```json\n{"calls": [{"tool": "system_health", "args": {}}]}\n```',
    '{"calls": [{"tool": "system_health", "args": {}}]}',
    'Voici :\n```\n[{"tool": "system_health", "arguments": "{}"}]\n```',
    '```json\n{"name": "system_health"}\n```',
])
def test_parse_accepts_common_shapes(reply):
    parsed = parse_calls(reply)
    assert parsed["count"] == 1
    assert parsed["calls"][0]["tool"] == "system_health"


def test_parse_rejects_prose_only():
    parsed = parse_calls("Je ne peux pas exécuter d'outil.")
    assert parsed["count"] == 0
    assert parsed["errors"] == []


def test_parse_reports_invalid_arguments():
    parsed = parse_calls('```json\n{"calls": [{"tool": "file_read", "arguments": "{oops"}]}\n```')
    assert parsed["count"] == 1
    assert "not valid JSON" in parsed["calls"][0]["error"]


def test_run_calls_executes_really(bridge, run):
    reply = '```json\n{"calls": [{"tool": "file_list", "args": {"path": "."}}, ' \
            '{"tool": "knowledge_stats", "args": {}}]}\n```'
    result = run(run_calls(bridge, reply))
    assert result["ok"] is True
    assert result["executed"] == 2
    assert "### OMNIBRIDGE RESULTS" in result["block"]
    assert "file_list" in result["block"]
    assert "Demo" in result["block"] or "README" in result["block"]


def test_run_calls_unknown_tool_is_reported_not_executed(bridge, run):
    result = run(run_calls(bridge, '```json\n{"calls": [{"tool": "ghost", "args": {}}]}\n```'))
    assert result["failed"] == 1
    assert "unknown tool" in result["block"]


def test_run_calls_level4_requires_explicit_confirm(bridge, cfg, run):
    cfg.permission_level = 2
    reply = '```json\n{"calls": [{"tool": "process_run", "args": {"action": "python_version"}}]}\n```'
    denied = run(run_calls(bridge, reply))
    assert denied["failed"] == 1
    assert "permission" in denied["block"].lower()

    cfg.permission_level = 4
    allowed = run(run_calls(bridge, reply, confirm=True))
    assert allowed["ok"] is True


def test_run_calls_no_calls(bridge, run):
    result = run(run_calls(bridge, "nothing here"))
    assert result["ok"] is False
    assert "No tool call" in result["error"]


def test_openai_tools_schema(bridge):
    tools = openai_tools(bridge)
    assert len(tools) == bridge.registry.size
    by_name = {t["function"]["name"]: t for t in tools}
    read = by_name["file_read"]["function"]
    assert read["parameters"]["type"] == "object"
    assert "path" in read["parameters"]["required"]
    assert read["parameters"]["properties"]["limit"]["type"] == "integer"
    assert "confirm" in by_name["process_run"]["function"]["parameters"]["properties"]
    json.dumps(tools)  # must be serialisable for any provider


@pytest.mark.parametrize("url", ["http://127.0.0.1:8765/mcp", "http://localhost:8765/mcp"])
def test_check_remote_mcp_reproaches_localhost(url, run):
    result = run(check_remote_mcp(url, "x"))
    assert result["chatgptReady"] is False
    assert any("https" in p for p in result["problems"])
    assert any("localhost" in p or "127.0.0.1" in p for p in result["problems"])


def test_check_remote_mcp_connection_failure(run):
    result = run(check_remote_mcp("https://127.0.0.1:9/mcp/x", "t", timeout_s=1.0))
    assert result["chatgptReady"] is False
    assert result["problems"]
