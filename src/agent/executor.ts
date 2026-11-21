import type { Db } from "../core/db.js";
import type { OmniBridgeConfig } from "../config.js";
import { log } from "../core/logger.js";
import type { Plan, PlanStep } from "./planner.js";

export type TaskStatus = "pending" | "running" | "paused" | "completed" | "failed" | "cancelled";

export interface StepResult {
  stepId: string;
  title: string;
  tool: string;
  ok: boolean;
  output: unknown;
  error?: string;
  attempts: number;
  finishedAt: string;
}

export interface TaskRecord {
  id: string;
  goal: string;
  status: TaskStatus;
  plan: Plan;
  results: Record<string, StepResult>;
  createdAt: string;
  updatedAt: string;
}

type ToolCaller = (name: string, args: Record<string, unknown>) => Promise<unknown>;

/**
 * Autonomous execution loop:
 * ANALYSE → PLANIFICATION → RECHERCHE → EXÉCUTION → TEST → INSPECTION → CORRECTION → VALIDATION
 * - checkpoint after every step (persisted, resumable after restart)
 * - configurable step/retry limits, cancellation, repeated-error detection
 * - dependency-ordered execution
 */
export class TaskExecutor {
  private tasks = new Map<string, TaskRecord>();
  private controllers = new Map<string, AbortController>();

  constructor(private cfg: OmniBridgeConfig, private db: Db, private callTool: ToolCaller) {}

  createTask(goal: string, plan: Plan): TaskRecord {
    const id = `task-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
    const now = new Date().toISOString();
    const rec: TaskRecord = { id, goal, status: "pending", plan, results: {}, createdAt: now, updatedAt: now };
    this.tasks.set(id, rec);
    this.persist(rec);
    return rec;
  }

  getTask(id: string): TaskRecord | null {
    const inMem = this.tasks.get(id);
    if (inMem) return inMem;
    const row = this.db.taskGet(id);
    if (!row) return null;
    const rec: TaskRecord = {
      id: String(row.id), goal: String(row.goal), status: row.status as TaskStatus,
      plan: row.plan as Plan, results: (row.results ?? {}) as Record<string, StepResult>,
      createdAt: String(row.created_at), updatedAt: String(row.updated_at),
    };
    this.tasks.set(id, rec);
    return rec;
  }

  listTasks(limit = 50) { return this.db.taskList(limit); }

  cancel(id: string): boolean {
    const rec = this.getTask(id);
    if (!rec) return false;
    rec.status = "cancelled";
    this.controllers.get(id)?.abort();
    this.persist(rec);
    return true;
  }

  private persist(rec: TaskRecord): void {
    rec.updatedAt = new Date().toISOString();
    this.db.taskUpsert(rec.id, rec.goal, rec.status, rec.plan, rec.results);
  }

  /** Run (or resume) a task. Respects dependencies; stops on repeated errors. */
  async run(id: string): Promise<TaskRecord> {
    const rec = this.getTask(id);
    if (!rec) throw new Error(`Unknown task: ${id}`);
    if (rec.status === "running") throw new Error(`Task ${id} is already running`);
    rec.status = "running";
    this.persist(rec);
    const ctrl = new AbortController();
    this.controllers.set(id, ctrl);

    const done = new Set(Object.keys(rec.results).filter((k) => rec.results[k]?.ok));
    const errorSignatures = new Map<string, number>();
    let executed = 0;

    try {
      let progress = true;
      while (progress && rec.status === "running") {
        progress = false;
        for (const step of rec.plan.steps) {
          if (rec.status !== "running" || ctrl.signal.aborted) break;
          if (done.has(step.id)) continue;
          if (!step.dependsOn.every((d) => done.has(d))) continue;
          if (executed >= this.cfg.agentMaxSteps) {
            rec.status = "failed";
            rec.results[step.id] = {
              stepId: step.id, title: step.title, tool: step.tool, ok: false,
              output: null, error: `Step limit reached (${this.cfg.agentMaxSteps})`, attempts: 0,
              finishedAt: new Date().toISOString(),
            };
            break;
          }
          progress = true;
          executed++;
          const result = await this.runStep(rec, step, errorSignatures);
          rec.results[step.id] = result;
          if (result.ok) done.add(step.id);
          this.db.checkpointAdd(rec.id, Object.keys(rec.results).length, { results: rec.results, done: [...done] });
          this.persist(rec);
          if (!result.ok && (errorSignatures.get(result.error ?? "") ?? 0) >= 3) {
            rec.status = "failed";
            log.warn("task stopped: repeated error", { task: rec.id, step: step.id });
            break;
          }
        }
      }
      if (rec.status === "running") {
        const allDone = rec.plan.steps.every((s) => done.has(s.id));
        rec.status = allDone ? "completed" : "failed";
      }
    } catch (e) {
      rec.status = "failed";
      log.error("task failed", { task: rec.id, error: String(e) });
    } finally {
      this.controllers.delete(id);
      this.persist(rec);
    }
    return rec;
  }

  private async runStep(rec: TaskRecord, step: PlanStep, errorSignatures: Map<string, number>): Promise<StepResult> {
    let lastError = "";
    for (let attempt = 1; attempt <= this.cfg.agentMaxRetries + 1; attempt++) {
      let timer: NodeJS.Timeout | undefined;
      try {
        const timeout = new Promise<never>((_, reject) => {
          timer = setTimeout(() => reject(new Error(`Step timed out after ${this.cfg.agentStepTimeoutMs}ms`)), this.cfg.agentStepTimeoutMs);
        });
        const output = await Promise.race([this.callTool(step.tool, step.args), timeout]);
        if (timer) clearTimeout(timer);
        return { stepId: step.id, title: step.title, tool: step.tool, ok: true, output, attempts: attempt, finishedAt: new Date().toISOString() };
      } catch (e) {
        if (timer) clearTimeout(timer);
        lastError = e instanceof Error ? e.message : String(e);
        errorSignatures.set(lastError, (errorSignatures.get(lastError) ?? 0) + 1);
        log.warn("step attempt failed", { task: rec.id, step: step.id, attempt, error: lastError });
      }
    }
    return { stepId: step.id, title: step.title, tool: step.tool, ok: false, output: null, error: lastError, attempts: this.cfg.agentMaxRetries + 1, finishedAt: new Date().toISOString() };
  }

  /** Restore the latest checkpoint snapshot for a task. */
  restoreCheckpoint(id: string): { restored: boolean; snapshot?: unknown } {
    const cp = this.db.checkpointLatest(id);
    if (!cp) return { restored: false };
    const rec = this.getTask(id);
    if (rec && cp.snapshot && typeof cp.snapshot === "object") {
      const snap = cp.snapshot as { results?: Record<string, StepResult> };
      if (snap.results) rec.results = snap.results;
      rec.status = "paused";
      this.persist(rec);
    }
    return { restored: true, snapshot: cp.snapshot };
  }
}
