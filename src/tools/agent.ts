import type { Registry } from "../core/registry.js";
import type { ToolDef } from "../core/permissions.js";
import type { TaskExecutor } from "../agent/executor.js";
import { createPlan, type Plan } from "../agent/planner.js";
import { ROLES, type AgentRole } from "../agent/roles.js";

export function registerAgentTools(reg: Registry, executor: TaskExecutor): void {
  const tools: ToolDef[] = [
    {
      name: "agent_create_plan",
      description: "Create an execution plan for a goal. Either pass explicit steps (each with a real tool name) or let the deterministic planner decompose the goal. Plans are dependency-ordered and checkpointed.",
      inputSchema: {
        type: "object",
        properties: {
          goal: { type: "string" },
          steps: { type: "array", items: { type: "object", properties: { title: { type: "string" }, tool: { type: "string" }, args: { type: "object", default: {} }, dependsOn: { type: "array", items: { type: "string" }, default: [] } }, required: ["title", "tool"] } },
          workspace: { type: "string", default: "." },
        },
        required: ["goal"],
      },
      level: 1, category: "agent", readOnly: true,
      handler: (args) => {
        const goal = String(args.goal);
        if (Array.isArray(args.steps) && args.steps.length) {
          const steps = (args.steps as Array<Record<string, unknown>>).map((s, i) => {
            const tool = String(s.tool);
            if (!reg.get(tool)) throw new Error(`Unknown tool in plan: ${tool}. Use system_list_tools to discover real tools.`);
            return {
              id: `s${i + 1}`, title: String(s.title), tool,
              args: (s.args as Record<string, unknown>) ?? {},
              role: "coordinator" as AgentRole,
              dependsOn: (s.dependsOn as string[]) ?? [],
              acceptance: "Step completes without error",
            };
          });
          return { goal, steps, rationale: "Plan fourni explicitement par l'appelant." } satisfies Plan;
        }
        return createPlan(goal, { workspace: String(args.workspace ?? ".") });
      },
    },
    {
      name: "agent_start_task",
      description: "Start (or resume) an autonomous task: creates a plan if needed, then executes it step by step with checkpoints, retries and cancellation. Returns the task id immediately and runs in the background.",
      inputSchema: {
        type: "object",
        properties: {
          goal: { type: "string" },
          plan: { type: "object", description: "Optional explicit plan (from agent_create_plan)" },
          workspace: { type: "string", default: "." },
        },
        required: ["goal"],
      },
      level: 2, category: "agent", readOnly: false,
      handler: async (args) => {
        const goal = String(args.goal);
        const plan = (args.plan as Plan | undefined) ?? createPlan(goal, { workspace: String(args.workspace ?? ".") });
        const rec = executor.createTask(goal, plan);
        // Fire-and-forget with error capture; status is queryable.
        executor.run(rec.id).catch(() => { /* status persisted */ });
        return { taskId: rec.id, status: rec.status, stepCount: plan.steps.length, plan };
      },
    },
    {
      name: "agent_get_task_status",
      description: "Get the status of an autonomous task: progress, per-step results, errors.",
      inputSchema: { type: "object", properties: { taskId: { type: "string" } }, required: ["taskId"] },
      level: 1, category: "agent", readOnly: true,
      handler: (args) => {
        const rec = executor.getTask(String(args.taskId));
        if (!rec) throw new Error(`Unknown task: ${args.taskId}`);
        const results = Object.values(rec.results);
        return {
          taskId: rec.id, goal: rec.goal, status: rec.status,
          completed: results.filter((r) => r.ok).length, failed: results.filter((r) => !r.ok).length,
          total: rec.plan.steps.length, results,
          createdAt: rec.createdAt, updatedAt: rec.updatedAt,
        };
      },
    },
    {
      name: "agent_cancel_task",
      description: "Cancel a running autonomous task. Already-completed steps keep their checkpoints.",
      inputSchema: { type: "object", properties: { taskId: { type: "string" } }, required: ["taskId"] },
      level: 2, category: "agent", readOnly: false,
      handler: (args) => ({ ok: executor.cancel(String(args.taskId)), taskId: String(args.taskId) }),
    },
    {
      name: "agent_review_result",
      description: "Review a task/step result: checks acceptance criteria, flags failures, and suggests next actions (retry, fix, or proceed).",
      inputSchema: { type: "object", properties: { taskId: { type: "string" }, stepId: { type: "string" } }, required: ["taskId"] },
      level: 1, category: "agent", readOnly: true,
      handler: (args) => {
        const rec = executor.getTask(String(args.taskId));
        if (!rec) throw new Error(`Unknown task: ${args.taskId}`);
        const stepId = args.stepId ? String(args.stepId) : undefined;
        const results = stepId ? [rec.results[stepId]].filter(Boolean) : Object.values(rec.results);
        const failed = results.filter((r) => !r.ok);
        return {
          taskId: rec.id, status: rec.status,
          reviewed: results.length, failed: failed.length,
          verdict: failed.length ? "needs-correction" : "ok",
          suggestions: failed.length
            ? failed.map((f) => `Step '${f.title}' failed: ${f.error}. Diagnose with error_diagnose, fix, then restore checkpoint and re-run.`)
            : ["All reviewed steps passed. Proceed to the next phase."],
          results,
        };
      },
    },
    {
      name: "agent_find_solution",
      description: "Search for solutions to a problem: combines knowledge retrieval, documentation search and web search into a ranked candidate list with sources.",
      inputSchema: { type: "object", properties: { problem: { type: "string" }, maxCandidates: { type: "integer", minimum: 1, maximum: 10, default: 5 } }, required: ["problem"] },
      level: 1, category: "agent", readOnly: true,
      handler: async (args, ctx) => {
        const problem = String(args.problem);
        const [kb, docs] = await Promise.all([
          ctx.callTool("knowledge_retrieve", { query: problem, limit: 5 }).catch(() => []),
          ctx.callTool("documentation_search", { query: problem, limit: 5 }).catch(() => ({})),
        ]);
        return {
          problem,
          candidates: [
            { source: "knowledge-base", hits: kb },
            { source: "documentation", result: docs },
          ],
          note: "Use agent_compare_solutions to evaluate candidates, then web_search/web_open for deeper research.",
        };
      },
    },
    {
      name: "agent_compare_solutions",
      description: "Compare candidate solutions in a structured matrix (pros/cons, complexity, risk) and recommend the best fit for the constraints. Deterministic scoring — no invented facts.",
      inputSchema: {
        type: "object",
        properties: {
          problem: { type: "string" },
          solutions: { type: "array", items: { type: "object", properties: { name: { type: "string" }, description: { type: "string", default: "" }, pros: { type: "array", items: { type: "string" }, default: [] }, cons: { type: "array", items: { type: "string" }, default: [] } }, required: ["name"] } },
          constraints: { type: "string", default: "" },
        },
        required: ["problem", "solutions"],
      },
      level: 1, category: "agent", readOnly: true,
      handler: (args) => {
        const solutions = args.solutions as Array<{ name: string; description?: string; pros?: string[]; cons?: string[] }>;
        if (!solutions.length) throw new Error("Provide at least one solution to compare.");
        const scored = solutions.map((s) => {
          const pros = s.pros ?? [], cons = s.cons ?? [];
          const score = pros.length - cons.length;
          return { name: s.name, description: s.description ?? "", pros, cons, score, complexity: cons.length > 2 ? "high" : cons.length > 0 ? "medium" : "low" };
        }).sort((a, b) => b.score - a.score);
        return {
          problem: String(args.problem), constraints: String(args.constraints ?? ""),
          ranking: scored,
          recommendation: scored[0].name,
          rationale: `Highest net score (${scored[0].score}). Verify with documentation_search before committing.`,
        };
      },
    },
    {
      name: "agent_create_checkpoint",
      description: "Create a manual checkpoint for a task (snapshot of current results). Checkpoints allow resuming after errors or restarts.",
      inputSchema: { type: "object", properties: { taskId: { type: "string" } }, required: ["taskId"] },
      level: 2, category: "agent", readOnly: false,
      handler: (args, ctx) => {
        const rec = executor.getTask(String(args.taskId));
        if (!rec) throw new Error(`Unknown task: ${args.taskId}`);
        const id = ctx.db.checkpointAdd(rec.id, Object.keys(rec.results).length, { results: rec.results });
        return { ok: true, checkpointId: id, taskId: rec.id };
      },
    },
    {
      name: "agent_restore_checkpoint",
      description: "Restore the latest checkpoint of a task and pause it, so it can be re-run from the saved state.",
      inputSchema: { type: "object", properties: { taskId: { type: "string" } }, required: ["taskId"] },
      level: 2, category: "agent", readOnly: false,
      handler: (args) => executor.restoreCheckpoint(String(args.taskId)),
    },
    {
      name: "agent_list_roles",
      description: "List the specialized agent roles (architect, researcher, developer, debugger, tester, optimizer, coordinator) with their tool preferences and checklists.",
      inputSchema: { type: "object", properties: {} },
      level: 1, category: "agent", readOnly: true,
      handler: () => Object.values(ROLES),
    },
  ];
  for (const t of tools) reg.register(t);
}
