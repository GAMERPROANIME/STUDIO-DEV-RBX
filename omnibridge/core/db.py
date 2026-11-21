"""SQLite storage (stdlib sqlite3): memory, knowledge FTS5, tasks, checkpoints, audit."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import Config
from .logger import log


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Db:
    def __init__(self, cfg: Config):
        cfg.data_dir.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(cfg.data_dir / "omnibridge.db"), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA foreign_keys=ON;")
        self._migrate()
        log.info("db ready", extra={"path": str(cfg.data_dir / "omnibridge.db")})

    def _migrate(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS memory (
                scope TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL,
                updated_at TEXT NOT NULL, PRIMARY KEY (scope, key)
            );
            CREATE TABLE IF NOT EXISTS knowledge_chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL, title TEXT NOT NULL, version TEXT DEFAULT '',
                fetched_at TEXT NOT NULL, reliability TEXT NOT NULL DEFAULT 'community',
                chunk_index INTEGER NOT NULL DEFAULT 0, text TEXT NOT NULL
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(
                text, title, source, content='knowledge_chunks', content_rowid='id'
            );
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY, goal TEXT NOT NULL, status TEXT NOT NULL,
                plan_json TEXT NOT NULL DEFAULT '[]', results_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS checkpoints (
                id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL,
                step_index INTEGER NOT NULL, snapshot_json TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, tool TEXT NOT NULL,
                level INTEGER NOT NULL, ok INTEGER NOT NULL, error TEXT DEFAULT ''
            );
            CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON knowledge_chunks BEGIN
                INSERT INTO knowledge_fts(rowid, text, title, source) VALUES (new.id, new.text, new.title, new.source);
            END;
            CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON knowledge_chunks BEGIN
                INSERT INTO knowledge_fts(knowledge_fts, rowid, text, title, source) VALUES('delete', old.id, old.text, old.title, old.source);
            END;
            """
        )
        self._conn.commit()

    # ---- memory ----
    def memory_set(self, scope: str, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO memory(scope,key,value,updated_at) VALUES(?,?,?,?) "
            "ON CONFLICT(scope,key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (scope, key, value, _now()),
        )
        self._conn.commit()

    def memory_get(self, scope: str, key: str) -> str | None:
        row = self._conn.execute("SELECT value FROM memory WHERE scope=? AND key=?", (scope, key)).fetchone()
        return row["value"] if row else None

    def memory_list(self, scope: str, prefix: str = "") -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT key,value,updated_at FROM memory WHERE scope=? AND key LIKE ? ORDER BY key",
            (scope, prefix + "%"),
        ).fetchall()
        return [dict(r) for r in rows]

    # ---- knowledge ----
    def knowledge_clear_source(self, source: str) -> None:
        self._conn.execute("DELETE FROM knowledge_chunks WHERE source=?", (source,))
        self._conn.commit()

    def knowledge_insert(self, source: str, title: str, version: str, reliability: str, chunk_index: int, text: str) -> int:
        cur = self._conn.execute(
            "INSERT INTO knowledge_chunks(source,title,version,fetched_at,reliability,chunk_index,text) VALUES(?,?,?,?,?,?,?)",
            (source, title, version, _now(), reliability, chunk_index, text),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def knowledge_search_fts(self, query: str, limit: int) -> list[dict[str, Any]]:
        try:
            rows = self._conn.execute(
                "SELECT c.id,c.source,c.title,c.version,c.fetched_at,c.reliability,c.chunk_index,c.text, "
                "bm25(knowledge_fts) AS rank FROM knowledge_fts f "
                "JOIN knowledge_chunks c ON c.id=f.rowid WHERE knowledge_fts MATCH ? ORDER BY rank LIMIT ?",
                (query, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.Error:
            return []

    def knowledge_all_chunks(self, limit: int = 20000) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT id,source,title,version,fetched_at,reliability,chunk_index,text FROM knowledge_chunks ORDER BY id LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def knowledge_stats(self) -> dict[str, Any]:
        chunks = self._conn.execute("SELECT COUNT(*) c FROM knowledge_chunks").fetchone()["c"]
        sources = self._conn.execute("SELECT COUNT(DISTINCT source) c FROM knowledge_chunks").fetchone()["c"]
        by_source = [
            dict(r)
            for r in self._conn.execute(
                "SELECT source, COUNT(*) chunks FROM knowledge_chunks GROUP BY source ORDER BY chunks DESC"
            ).fetchall()
        ]
        return {"chunks": chunks, "sources": sources, "bySource": by_source}

    # ---- tasks / checkpoints ----
    def task_upsert(self, task_id: str, goal: str, status: str, plan: Any, results: Any) -> None:
        now = _now()
        self._conn.execute(
            "INSERT INTO tasks(id,goal,status,plan_json,results_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET goal=excluded.goal,status=excluded.status,"
            "plan_json=excluded.plan_json,results_json=excluded.results_json,updated_at=excluded.updated_at",
            (task_id, goal, status, json.dumps(plan), json.dumps(results), now, now),
        )
        self._conn.commit()

    def task_get(self, task_id: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["plan"] = json.loads(d.pop("plan_json"))
        d["results"] = json.loads(d.pop("results_json"))
        return d

    def task_list(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT id,goal,status,created_at,updated_at FROM tasks ORDER BY updated_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def checkpoint_add(self, task_id: str, step_index: int, snapshot: Any) -> int:
        cur = self._conn.execute(
            "INSERT INTO checkpoints(task_id,step_index,snapshot_json,created_at) VALUES(?,?,?,?)",
            (task_id, step_index, json.dumps(snapshot), _now()),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def checkpoint_latest(self, task_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM checkpoints WHERE task_id=? ORDER BY step_index DESC, id DESC LIMIT 1", (task_id,)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["snapshot"] = json.loads(d.pop("snapshot_json"))
        return d

    # ---- audit ----
    def audit(self, tool: str, level: int, ok: bool, error: str = "") -> None:
        self._conn.execute(
            "INSERT INTO audit(ts,tool,level,ok,error) VALUES(?,?,?,?,?)",
            (_now(), tool, level, 1 if ok else 0, error[:500]),
        )
        self._conn.commit()

    def audit_recent(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._conn.execute("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        self._conn.close()
