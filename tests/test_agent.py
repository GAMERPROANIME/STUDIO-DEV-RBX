"""Autonomous loop: planning, execution, checkpoints, cancellation, review."""
from __future__ import annotations

import asyncio

from omnibridge.agent.planner import create_plan


def test_plan_uses_real_tools(bridge):
    plan = create_plan("Build a Roblox combat arena", ".")
    assert len(plan.steps) >= 5
    for step in plan.steps:
        assert bridge.registry.get(step.tool) is not None, f"plan references unknown tool {step.tool}"
    assert any(s.tool == "file_update" for s in plan.steps)


def test_plan_for_research_goal(bridge):
    plan = create_plan("Research the current MCP specification", ".")
    tools = [s.tool for s in plan.steps]
    assert "web_search" in tools and "web_compare_sources" in tools


def test_plan_for_debug_goal(bridge):
    tools = [s.tool for s in create_plan("Corriger un bug de collision", ".").steps]
    assert tools[0] == "project_inspect"
    assert "error_diagnose" in tools


def test_agent_roles_cover_catalogue(bridge):
    from omnibridge.agent.roles import ROLES, role_for_tool

    assert len(ROLES) >= 5
    for tool in bridge.registry.list():
        assert role_for_tool(tool.name) in ROLES


def test_task_runs_to_completion(bridge, run):
    async def scenario():
        started = await bridge.call_tool("agent_start_task", {"goal": "Build a Roblox combat system"})
        task_id = started["taskId"]
        assert started["stepCount"] >= 5
        for _ in range(200):
            status = await bridge.call_tool("agent_get_task_status", {"taskId": task_id})
            if status["status"] not in ("running", "pending"):
                break
            await asyncio.sleep(0.05)
        return status

    status = run(scenario())
    assert status["status"] == "completed", status
    assert status["failed"] == 0
    assert all(r["ok"] for r in status["results"])


def test_task_checkpoint_restore(bridge, run):
    async def scenario():
        started = await bridge.call_tool("agent_start_task", {"goal": "Inspect project structure"})
        task_id = started["taskId"]
        for _ in range(200):
            status = await bridge.call_tool("agent_get_task_status", {"taskId": task_id})
            if status["status"] not in ("running", "pending"):
                break
            await asyncio.sleep(0.05)
        restored = await bridge.call_tool("agent_restore_checkpoint", {"taskId": task_id})
        return status, restored

    status, restored = run(scenario())
    assert status["status"] == "completed"
    assert restored["restored"] is True


def test_task_review_reports_ok(bridge, run):
    async def scenario():
        started = await bridge.call_tool("agent_start_task", {"goal": "Inspect the project"})
        task_id = started["taskId"]
        for _ in range(200):
            status = await bridge.call_tool("agent_get_task_status", {"taskId": task_id})
            if status["status"] not in ("running", "pending"):
                break
            await asyncio.sleep(0.05)
        return await bridge.call_tool("agent_review_result", {"taskId": task_id})

    review = run(scenario())
    assert review["verdict"] == "ok"


def test_task_cancel(bridge, run):
    async def scenario():
        started = await bridge.call_tool("agent_start_task", {"goal": "Research Roblox DataStore limits"})
        cancelled = await bridge.call_tool("agent_cancel_task", {"taskId": started["taskId"]})
        return started, cancelled

    started, cancelled = run(scenario())
    assert started["taskId"]
    assert cancelled["ok"] is True


def test_plan_with_unknown_tool_is_rejected(bridge, run):
    try:
        run(bridge.call_tool("agent_create_plan", {
            "goal": "x", "steps": [{"title": "x", "tool": "not_a_tool"}]}))
    except ValueError as e:
        assert "not_a_tool" in str(e)
    else:
        raise AssertionError("unknown tool in plan must be rejected")


def test_compare_solutions_scores(bridge, run):
    res = run(bridge.call_tool("agent_compare_solutions", {
        "problem": "state replication",
        "solutions": [
            {"name": "RemoteEvents", "pros": ["standard", "simple"], "cons": ["manual validation"]},
            {"name": "Direct client writes", "pros": ["fast"], "cons": ["insecure", "exploitable", "desync"]},
        ],
    }))
    assert res["recommendation"] == "RemoteEvents"
    assert res["ranking"][0]["score"] > res["ranking"][1]["score"]
