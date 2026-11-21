import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { DatabaseSync } from "node:sqlite";
import type { OmniBridgeConfig } from "../config.js";
import { log } from "./logger.js";

/**
 * SQLite storage (node:sqlite, no native deps).
 * Tables:
 *  - memory(scope, key, value, updated_at)  — personal / project / temp memory
 *  - knowledge_chunks(id, source, title, version, fetched_at, reliability, chunk_index, text)
 *  - knowledge_fts (FTS5 virtual table over chunks)
 *  - tasks(id, goal, status, plan_json, results_json, created_at, updated_at)
 *  - checkpoints(id, task_id, step_index, snapshot_json, created_at)
 *  - audit(id, ts, tool, level, args_hash, ok, error)
 */
export class Db {
  private db: DatabaseSync;

  constructor(cfg: OmniBridgeConfig) {
    mkdirSync(cfg.dataDir, { recursive: true });
    this.db = new DatabaseSync(join(cfg.dataDir, "omnibridge.db"));
    this.db.exec("PRAGMA journal_mode=WAL;");
    this.db.exec("PRAGMA foreign_keys=ON;");
    this.migrate();
    log.info("db ready", { path: join(cfg.dataDir, "omnibridge.db") });
  }

  private migrate(): void {
    this.db.exec(`
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
    `);
    // Keep FTS in sync via triggers.
    this.db.exec(`
      CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON knowledge_chunks BEGIN
        INSERT INTO knowledge_fts(rowid, text, title, source) VALUES (new.id, new.text, new.title, new.source);
      END;
      CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON knowledge_chunks BEGIN
        INSERT INTO knowledge_fts(knowledge_fts, rowid, text, title, source) VALUES('delete', old.id, old.text, old.title, old.source);
      END;
    `);
  }

  // ---- memory ----
  memorySet(scope: string, key: string, value: string): void {
    this.db.prepare(
      `INSERT INTO memory(scope,key,value,updated_at) VALUES(?,?,?,?)
       ON CONFLICT(scope,key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at`
    ).run(scope, key, value, new Date().toISOString());
  }
  memoryGet(scope: string, key: string): string | null {
    const row = this.db.prepare(`SELECT value FROM memory WHERE scope=? AND key=?`).get(scope, key) as { value: string } | undefined;
    return row?.value ?? null;
  }
  memoryList(scope: string, prefix = ""): Array<{ key: string; value: string; updated_at: string }> {
    return this.db.prepare(
      `SELECT key,value,updated_at FROM memory WHERE scope=? AND key LIKE ? ORDER BY key`
    ).all(scope, prefix + "%") as Array<{ key: string; value: string; updated_at: string }>;
  }
  memoryDelete(scope: string, key: string): boolean {
    const r = this.db.prepare(`DELETE FROM memory WHERE scope=? AND key=?`).run(scope, key);
    return Number(r.changes) > 0;
  }

  // ---- knowledge ----
  knowledgeClearSource(source: string): void {
    this.db.prepare(`DELETE FROM knowledge_chunks WHERE source=?`).run(source);
  }
  knowledgeInsert(source: string, title: string, version: string, reliability: string, chunkIndex: number, text: string): number {
    const r = this.db.prepare(
      `INSERT INTO knowledge_chunks(source,title,version,fetched_at,reliability,chunk_index,text)
       VALUES(?,?,?,?,?,?,?)`
    ).run(source, title, version, new Date().toISOString(), reliability, chunkIndex, text);
    return Number(r.lastInsertRowid);
  }
  knowledgeSearchFts(query: string, limit: number): Array<Record<string, unknown>> {
    try {
      return this.db.prepare(
        `SELECT c.id,c.source,c.title,c.version,c.fetched_at,c.reliability,c.chunk_index,c.text,
                bm25(knowledge_fts) AS rank
         FROM knowledge_fts f JOIN knowledge_chunks c ON c.id=f.rowid
         WHERE knowledge_fts MATCH ? ORDER BY rank LIMIT ?`
      ).all(query, limit) as Array<Record<string, unknown>>;
    } catch {
      return [];
    }
  }
  knowledgeAllChunks(limit = 5000): Array<Record<string, unknown>> {
    return this.db.prepare(
      `SELECT id,source,title,version,fetched_at,reliability,chunk_index,text FROM knowledge_chunks ORDER BY id LIMIT ?`
    ).all(limit) as Array<Record<string, unknown>>;
  }
  knowledgeStats(): { chunks: number; sources: number; bySource: Array<{ source: string; chunks: number }> } {
    const chunks = (this.db.prepare(`SELECT COUNT(*) c FROM knowledge_chunks`).get() as { c: number }).c;
    const sources = (this.db.prepare(`SELECT COUNT(DISTINCT source) c FROM knowledge_chunks`).get() as { c: number }).c;
    const bySource = this.db.prepare(
      `SELECT source, COUNT(*) chunks FROM knowledge_chunks GROUP BY source ORDER BY chunks DESC`
    ).all() as Array<{ source: string; chunks: number }>;
    return { chunks, sources, bySource };
  }

  // ---- tasks / checkpoints ----
  taskUpsert(id: string, goal: string, status: string, plan: unknown, results: unknown): void {
    const now = new Date().toISOString();
    this.db.prepare(
      `INSERT INTO tasks(id,goal,status,plan_json,results_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?)
       ON CONFLICT(id) DO UPDATE SET goal=excluded.goal,status=excluded.status,
         plan_json=excluded.plan_json,results_json=excluded.results_json,updated_at=excluded.updated_at`
    ).run(id, goal, status, JSON.stringify(plan), JSON.stringify(results), now, now);
  }
  taskGet(id: string): Record<string, unknown> | null {
    const row = this.db.prepare(`SELECT * FROM tasks WHERE id=?`).get(id) as Record<string, unknown> | undefined;
    if (!row) return null;
    return { ...row, plan: JSON.parse(String(row.plan_json)), results: JSON.parse(String(row.results_json)) };
  }
  taskList(limit = 50): Array<Record<string, unknown>> {
    return (this.db.prepare(`SELECT id,goal,status,created_at,updated_at FROM tasks ORDER BY updated_at DESC LIMIT ?`)
      .all(limit) as Array<Record<string, unknown>>);
  }
  checkpointAdd(taskId: string, stepIndex: number, snapshot: unknown): number {
    const r = this.db.prepare(
      `INSERT INTO checkpoints(task_id,step_index,snapshot_json,created_at) VALUES(?,?,?,?)`
    ).run(taskId, stepIndex, JSON.stringify(snapshot), new Date().toISOString());
    return Number(r.lastInsertRowid);
  }
  checkpointLatest(taskId: string): Record<string, unknown> | null {
    const row = this.db.prepare(
      `SELECT * FROM checkpoints WHERE task_id=? ORDER BY step_index DESC, id DESC LIMIT 1`
    ).get(taskId) as Record<string, unknown> | undefined;
    if (!row) return null;
    return { ...row, snapshot: JSON.parse(String(row.snapshot_json)) };
  }

  // ---- audit ----
  audit(tool: string, level: number, ok: boolean, error = ""): void {
    this.db.prepare(`INSERT INTO audit(ts,tool,level,ok,error) VALUES(?,?,?,?,?)`)
      .run(new Date().toISOString(), tool, level, ok ? 1 : 0, error.slice(0, 500));
  }
  auditRecent(limit = 100): Array<Record<string, unknown>> {
    return this.db.prepare(`SELECT * FROM audit ORDER BY id DESC LIMIT ?`).all(limit) as Array<Record<string, unknown>>;
  }

  close(): void { this.db.close(); }
}
