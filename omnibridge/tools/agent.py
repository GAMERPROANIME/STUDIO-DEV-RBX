"""Autonomous agent tools: planning, execution, review, solution search."""
from __future__ import annotations

import asyncio

from ..agent.executor import TaskExecutor
from ..agent.planner import Plan, PlanStep, create_plan
from ..agent.roles import ROLES
from ..core.permissions import ToolDef
from ..core.registry import Registry


def register_agent_tools(reg: Registry, executor: TaskExecutor) -> None:
    async def create_plan_tool(args: dict, ctx) -> dict:
        goal = str(args["goal"])
        steps_in = args.get("steps")
        if isinstance(steps_in, list) and steps_in:
            steps: list[PlanStep] = []
            for i, s in enumerate(steps_in):
                tool = str(s["tool"])
                if not reg.get(tool):
                    raise ValueError(f"Unknown tool in plan: {tool}. Use system_list_tools to discover real tools.")
                steps.append(PlanStep(id=f"s{i + 1}", title=str(s["title"]), tool=tool,
                                      args=s.get("args") or {}, role="coordinator",
                                      depends_on=s.get("dependsOn") or [],
                                      acceptance="Step completes without error"))
            return Plan(goal=goal, steps=steps, rationale="Plan fourni explicitement par l'appelant.").to_dict()
        return create_plan(goal, str(args.get("workspace", "."))).to_dict()

    async def start_task(args: dict, ctx) -> dict:
        goal = str(args["goal"])
        plan_in = args.get("plan")
        if isinstance(plan_in, dict) and plan_in.get("steps"):
            steps = [PlanStep(id=s["id"], title=s["title"], tool=s["tool"], args=s.get("args") or {},
                              role=s.get("role", "coordinator"), depends_on=s.get("dependsOn") or [],
                              acceptance=s.get("acceptance", "")) for s in plan_in["steps"]]
            plan = Plan(goal=goal, steps=steps, rationale=plan_in.get("rationale", ""))
        else:
            plan = create_plan(goal, str(args.get("workspace", ".")))
        rec = executor.create_task(goal, plan)
        asyncio.create_task(executor.run(rec.id))
        return {"taskId": rec.id, "status": rec.status, "stepCount": len(plan.steps), "plan": plan.to_dict()}

    async def get_status(args: dict, ctx) -> dict:
        rec = executor.get_task(str(args["taskId"]))
        if not rec:
            raise ValueError(f"Unknown task: {args['taskId']}")
        results = list(rec.results.values())
        return {"taskId": rec.id, "goal": rec.goal, "status": rec.status,
                "completed": sum(1 for r in results if r.ok), "failed": sum(1 for r in results if not r.ok),
                "total": len(rec.plan.steps), "results": [r.to_dict() for r in results],
                "createdAt": rec.created_at, "updatedAt": rec.updated_at}

    async def cancel_task(args: dict, ctx) -> dict:
        return {"ok": executor.cancel(str(args["taskId"])), "taskId": str(args["taskId"])}

    async def review_result(args: dict, ctx) -> dict:
        rec = executor.get_task(str(args["taskId"]))
        if not rec:
            raise ValueError(f"Unknown task: {args['taskId']}")
        step_id = args.get("stepId")
        results = [rec.results[str(step_id)]] if step_id and str(step_id) in rec.results else list(rec.results.values())
        failed = [r for r in results if not r.ok]
        return {"taskId": rec.id, "status": rec.status, "reviewed": len(results), "failed": len(failed),
                "verdict": "needs-correction" if failed else "ok",
                "suggestions": ([f"Step '{f.title}' failed: {f.error}. Diagnose with error_diagnose, fix, "
                                 "then restore checkpoint and re-run." for f in failed]
                                or ["All reviewed steps passed. Proceed to the next phase."]),
                "results": [r.to_dict() for r in results]}

    async def find_solution(args: dict, ctx) -> dict:
        problem = str(args["problem"])
        kb = await ctx.call_tool("knowledge_retrieve", {"query": problem, "limit": 5})
        docs = await ctx.call_tool("documentation_search", {"query": problem, "limit": 5})
        return {"problem": problem,
                "candidates": [{"source": "knowledge-base", "hits": kb},
                               {"source": "documentation", "result": docs}],
                "note": "Use agent_compare_solutions to evaluate candidates, then web_search/web_open for deeper research."}

    async def compare_solutions(args: dict, ctx) -> dict:
        solutions = args["solutions"]
        if not solutions:
            raise ValueError("Provide at least one solution to compare.")
        scored = []
        for s in solutions:
            pros, cons = s.get("pros") or [], s.get("cons") or []
            scored.append({"name": s["name"], "description": s.get("description", ""), "pros": pros, "cons": cons,
                           "score": len(pros) - len(cons),
                           "complexity": "high" if len(cons) > 2 else "medium" if cons else "low"})
        scored.sort(key=lambda x: x["score"], reverse=True)
        return {"problem": str(args["problem"]), "constraints": str(args.get("constraints", "")),
                "ranking": scored, "recommendation": scored[0]["name"],
                "rationale": f"Highest net score ({scored[0]['score']}). Verify with documentation_search before committing."}

    async def create_checkpoint(args: dict, ctx) -> dict:
        rec = executor.get_task(str(args["taskId"]))
        if not rec:
            raise ValueError(f"Unknown task: {args['taskId']}")
        cid = ctx.db.checkpoint_add(rec.id, len(rec.results),
                                    {"results": {k: v.to_dict() for k, v in rec.results.items()}})
        return {"ok": True, "checkpointId": cid, "taskId": rec.id}

    async def restore_checkpoint(args: dict, ctx) -> dict:
        return executor.restore_checkpoint(str(args["taskId"]))

    async def list_roles(args: dict, ctx) -> list[dict]:
        return [r.to_dict() for r in ROLES.values()]

    reg.register(ToolDef("agent_create_plan",
                         "Create an execution plan for a goal. Either pass explicit steps (each with a real "
                         "tool name) or let the deterministic planner decompose the goal.",
                         {"goal": {"type": "string"},
                          "steps": {"type": "array", "items": {"type": "object"}, "default": []},
                          "workspace": {"type": "string", "default": "."}},
                         ["goal"], 1, "agent", True, create_plan_tool))
    reg.register(ToolDef("agent_start_task",
                         "Start (or resume) an autonomous task: creates a plan if needed, then executes it "
                         "step by step with checkpoints, retries and cancellation. Runs in the background.",
                         {"goal": {"type": "string"}, "plan": {"type": "object"},
                          "workspace": {"type": "string", "default": "."}},
                         ["goal"], 2, "agent", False, start_task))
    reg.register(ToolDef("agent_get_task_status",
                         "Get the status of an autonomous task: progress, per-step results, errors.",
                         {"taskId": {"type": "string"}}, ["taskId"], 1, "agent", True, get_status))
    reg.register(ToolDef("agent_cancel_task",
                         "Cancel a running autonomous task. Already-completed steps keep their checkpoints.",
                         {"taskId": {"type": "string"}}, ["taskId"], 2, "agent", False, cancel_task))
    reg.register(ToolDef("agent_review_result",
                         "Review a task/step result: checks acceptance criteria, flags failures, suggests next actions.",
                         {"taskId": {"type": "string"}, "stepId": {"type": "string"}},
                         ["taskId"], 1, "agent", True, review_result))
    reg.register(ToolDef("agent_find_solution",
                         "Search for solutions to a problem: knowledge retrieval + documentation search "
                         "into a ranked candidate list with sources.",
                         {"problem": {"type": "string"},
                          "maxCandidates": {"type": "integer", "default": 5, "minimum": 1, "maximum": 10}},
                         ["problem"], 1, "agent", True, find_solution))
    reg.register(ToolDef("agent_compare_solutions",
                         "Compare candidate solutions in a structured matrix (pros/cons, complexity, risk) "
                         "and recommend the best fit. Deterministic scoring — no invented facts.",
                         {"problem": {"type": "string"}, "solutions": {"type": "array", "items": {"type": "object"}},
                          "constraints": {"type": "string", "default": ""}},
                         ["problem", "solutions"], 1, "agent", True, compare_solutions))
    reg.register(ToolDef("agent_create_checkpoint",
                         "Create a manual checkpoint for a task (snapshot of current results).",
                         {"taskId": {"type": "string"}}, ["taskId"], 2, "agent", False, create_checkpoint))
    reg.register(ToolDef("agent_restore_checkpoint",
                         "Restore the latest checkpoint of a task and pause it, so it can be re-run from the saved state.",
                         {"taskId": {"type": "string"}}, ["taskId"], 2, "agent", False, restore_checkpoint))
    reg.register(ToolDef("agent_list_roles",
                         "List the specialized agent roles with their tool preferences and checklists.",
                         {}, [], 1, "agent", True, list_roles))
