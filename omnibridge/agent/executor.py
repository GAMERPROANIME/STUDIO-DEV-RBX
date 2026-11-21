"""Autonomous execution loop (asyncio): checkpoints, retries, cancellation, repeated-error detection."""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from ..config import Config
from ..core.db import Db
from ..core.logger import log
from .planner import Plan, PlanStep

ToolCaller = Callable[[str, dict], Awaitable[Any]]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class StepResult:
    step_id: str
    title: str
    tool: str
    ok: bool
    output: Any = None
    error: str = ""
    attempts: int = 0
    finished_at: str = ""
    role: str = "coordinator"

    def to_dict(self) -> dict:
        return {"stepId": self.step_id, "title": self.title, "tool": self.tool, "ok": self.ok,
                "role": self.role, "output": self.output, "error": self.error,
                "attempts": self.attempts, "finishedAt": self.finished_at}


@dataclass
class TaskRecord:
    id: str
    goal: str
    status: str  # pending | running | paused | completed | failed | cancelled
    plan: Plan
    results: dict[str, StepResult] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        return {"id": self.id, "goal": self.goal, "status": self.status,
                "plan": self.plan.to_dict(),
                "results": {k: v.to_dict() for k, v in self.results.items()},
                "createdAt": self.created_at, "updatedAt": self.updated_at}


class TaskExecutor:
    def __init__(self, cfg: Config, db: Db, call_tool: ToolCaller):
        self._cfg = cfg
        self._db = db
        self._call_tool = call_tool
        self._tasks: dict[str, TaskRecord] = {}
        self._running: dict[str, asyncio.Task] = {}

    def create_task(self, goal: str, plan: Plan) -> TaskRecord:
        task_id = f"task-{int(time.time() * 1000):x}-{uuid.uuid4().hex[:5]}"
        rec = TaskRecord(id=task_id, goal=goal, status="pending", plan=plan,
                         created_at=_now(), updated_at=_now())
        self._tasks[task_id] = rec
        self._persist(rec)
        return rec

    def get_task(self, task_id: str) -> TaskRecord | None:
        if task_id in self._tasks:
            return self._tasks[task_id]
        row = self._db.task_get(task_id)
        if not row:
            return None
        plan = Plan(goal=row["goal"], rationale="",
                    steps=[PlanStep(id=s["id"], title=s["title"], tool=s["tool"], args=s.get("args", {}),
                                    role=s.get("role", "coordinator"), depends_on=s.get("dependsOn", []),
                                    acceptance=s.get("acceptance", "")) for s in row["plan"].get("steps", [])])
        results = {k: StepResult(step_id=v["stepId"], title=v["title"], tool=v["tool"], ok=v["ok"],
                                 output=v.get("output"), error=v.get("error", ""), attempts=v.get("attempts", 0),
                                 finished_at=v.get("finishedAt", "")) for k, v in (row["results"] or {}).items()}
        rec = TaskRecord(id=row["id"], goal=row["goal"], status=row["status"], plan=plan, results=results,
                         created_at=row["created_at"], updated_at=row["updated_at"])
        self._tasks[task_id] = rec
        return rec

    @staticmethod
    def role_progress(rec: TaskRecord) -> dict[str, dict[str, int]]:
        """Multi-agent view: which role owns which steps and how far it got."""
        progress: dict[str, dict[str, int]] = {}
        for step in rec.plan.steps:
            bucket = progress.setdefault(step.role, {"steps": 0, "done": 0, "failed": 0})
            bucket["steps"] += 1
            result = rec.results.get(step.id)
            if result is None:
                continue
            bucket["done" if result.ok else "failed"] += 1
        return progress

    def list_tasks(self, limit: int = 50) -> list[dict[str, Any]]:
        return self._db.task_list(limit)

    def cancel(self, task_id: str) -> bool:
        rec = self.get_task(task_id)
        if not rec:
            return False
        rec.status = "cancelled"
        task = self._running.get(task_id)
        if task:
            task.cancel()
        self._persist(rec)
        return True

    def _persist(self, rec: TaskRecord) -> None:
        rec.updated_at = _now()
        self._db.task_upsert(rec.id, rec.goal, rec.status, rec.plan.to_dict(),
                             {k: v.to_dict() for k, v in rec.results.items()})

    async def run(self, task_id: str) -> TaskRecord:
        rec = self.get_task(task_id)
        if not rec:
            raise ValueError(f"Unknown task: {task_id}")
        if rec.status == "running":
            raise ValueError(f"Task {task_id} is already running")
        rec.status = "running"
        self._persist(rec)
        self._running[task_id] = asyncio.current_task()
        done = {k for k, v in rec.results.items() if v.ok}
        error_sigs: dict[str, int] = {}
        executed = 0
        try:
            progress = True
            while progress and rec.status == "running":
                progress = False
                for step in rec.plan.steps:
                    if rec.status != "running":
                        break
                    if step.id in done:
                        continue
                    if not all(d in done for d in step.depends_on):
                        continue
                    if executed >= self._cfg.agent_max_steps:
                        rec.status = "failed"
                        rec.results[step.id] = StepResult(step.id, step.title, step.tool, False, None,
                                                      f"Step limit reached ({self._cfg.agent_max_steps})", 0,
                                                      _now(), step.role)
                        break
                    progress = True
                    executed += 1
                    result = await self._run_step(rec, step, error_sigs)
                    rec.results[step.id] = result
                    if result.ok:
                        done.add(step.id)
                    self._db.checkpoint_add(rec.id, len(rec.results),
                                            {"results": {k: v.to_dict() for k, v in rec.results.items()},
                                             "done": sorted(done)})
                    self._persist(rec)
                    if not result.ok and error_sigs.get(result.error, 0) >= 3:
                        rec.status = "failed"
                        log.warning("task stopped: repeated error", extra={"task": rec.id, "step": step.id})
                        break
            if rec.status == "running":
                rec.status = "completed" if all(s.id in done for s in rec.plan.steps) else "failed"
        except asyncio.CancelledError:
            rec.status = "cancelled"
        except Exception as e:  # noqa: BLE001
            rec.status = "failed"
            log.error("task failed", extra={"task": rec.id, "error": str(e)})
        finally:
            self._running.pop(task_id, None)
            self._persist(rec)
        return rec

    async def _run_step(self, rec: TaskRecord, step: PlanStep, error_sigs: dict[str, int]) -> StepResult:
        last_error = ""
        # A plan may reference the task it belongs to before the task id exists.
        args = {k: (rec.id if k == "taskId" and v in ("pending", None, "") else v) for k, v in step.args.items()}
        for attempt in range(1, self._cfg.agent_max_retries + 2):
            try:
                output = await asyncio.wait_for(
                    self._call_tool(step.tool, args), timeout=self._cfg.agent_step_timeout_s)
                return StepResult(step.id, step.title, step.tool, True, output, "", attempt, _now(), step.role)
            except Exception as e:  # noqa: BLE001
                last_error = str(e)
                error_sigs[last_error] = error_sigs.get(last_error, 0) + 1
                log.warning("step attempt failed", extra={"task": rec.id, "step": step.id,
                                                          "attempt": attempt, "error": last_error})
        return StepResult(step.id, step.title, step.tool, False, None, last_error,
                          self._cfg.agent_max_retries + 1, _now(), step.role)

    def restore_checkpoint(self, task_id: str) -> dict[str, Any]:
        cp = self._db.checkpoint_latest(task_id)
        if not cp:
            return {"restored": False}
        rec = self.get_task(task_id)
        snap = cp["snapshot"]
        if rec and isinstance(snap, dict) and snap.get("results"):
            rec.results = {k: StepResult(step_id=v["stepId"], title=v["title"], tool=v["tool"], ok=v["ok"],
                                         output=v.get("output"), error=v.get("error", ""),
                                         attempts=v.get("attempts", 0), finished_at=v.get("finishedAt", ""),
                                         role=v.get("role", "coordinator"))
                           for k, v in snap["results"].items()}
            rec.status = "paused"
            self._persist(rec)
        return {"restored": True, "snapshot": snap}
