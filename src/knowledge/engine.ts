import type { Db } from "../core/db.js";
import { redactSecrets } from "../core/permissions.js";

export interface KnowledgeHit {
  id: number;
  source: string;
  title: string;
  version: string;
  fetchedAt: string;
  reliability: string;
  chunkIndex: number;
  text: string;
  score: number;
  /** Citation string the agent must include when using this fact. */
  citation: string;
}

const CHUNK_SIZE = 1200;
const OVERLAP = 200;

export function chunkText(text: string): string[] {
  const clean = text.replace(/\r\n/g, "\n").trim();
  if (!clean) return [];
  const chunks: string[] = [];
  let start = 0;
  while (start < clean.length) {
    let end = Math.min(start + CHUNK_SIZE, clean.length);
    if (end < clean.length) {
      const breakAt = clean.lastIndexOf("\n", end);
      if (breakAt > start + CHUNK_SIZE * 0.4) end = breakAt;
    }
    chunks.push(clean.slice(start, end).trim());
    if (end >= clean.length) break;
    start = Math.max(end - OVERLAP, start + 1);
  }
  return chunks.filter((c) => c.length > 20);
}

function tokenize(text: string): string[] {
  return text.toLowerCase().match(/[a-z0-9_]{2,}/g) ?? [];
}

/** TF-IDF scoring over the full chunk corpus (hybrid with FTS5 ranking). */
function tfidfScore(query: string, chunks: Array<Record<string, unknown>>): Map<number, number> {
  const qTokens = tokenize(query);
  const scores = new Map<number, number>();
  if (!qTokens.length || !chunks.length) return scores;
  const df = new Map<string, number>();
  const docs = chunks.map((c) => ({ id: Number(c.id), tokens: tokenize(String(c.text)) }));
  for (const d of docs) {
    for (const t of new Set(d.tokens)) df.set(t, (df.get(t) ?? 0) + 1);
  }
  const N = docs.length;
  for (const d of docs) {
    let s = 0;
    const tf = new Map<string, number>();
    for (const t of d.tokens) tf.set(t, (tf.get(t) ?? 0) + 1);
    for (const q of qTokens) {
      const f = tf.get(q);
      if (!f) continue;
      const idf = Math.log(1 + N / (1 + (df.get(q) ?? 0)));
      s += (1 + Math.log(f)) * idf;
    }
    if (s > 0) scores.set(d.id, s);
  }
  return scores;
}

export class KnowledgeEngine {
  constructor(private db: Db) {}

  /** Index a document: replaces previous chunks from the same source. */
  indexDocument(opts: {
    source: string; title: string; version?: string;
    reliability?: "official" | "community" | "project" | "web";
    text: string;
  }): { chunks: number } {
    const { source, title, text } = opts;
    this.db.knowledgeClearSource(source);
    const chunks = chunkText(redactSecrets(text));
    chunks.forEach((c, i) =>
      this.db.knowledgeInsert(source, title, opts.version ?? "", opts.reliability ?? "project", i, c)
    );
    return { chunks: chunks.length };
  }

  /** Hybrid retrieval: FTS5 candidates + TF-IDF re-rank, with citations. */
  retrieve(query: string, limit = 8): KnowledgeHit[] {
    const ftsQuery = tokenize(query).join(" OR ");
    const ftsHits = ftsQuery ? this.db.knowledgeSearchFts(ftsQuery, Math.max(limit * 4, 40)) : [];
    const all = this.db.knowledgeAllChunks(20000);
    const tfidf = tfidfScore(query, all);
    const byId = new Map<number, Record<string, unknown>>();
    for (const c of all) byId.set(Number(c.id), c);
    for (const h of ftsHits) byId.set(Number(h.id), h);

    const scored: KnowledgeHit[] = [];
    for (const [id, c] of byId) {
      const score = tfidf.get(id) ?? 0;
      if (score <= 0) continue;
      const source = String(c.source);
      scored.push({
        id,
        source,
        title: String(c.title),
        version: String(c.version ?? ""),
        fetchedAt: String(c.fetched_at ?? ""),
        reliability: String(c.reliability ?? "community"),
        chunkIndex: Number(c.chunk_index ?? 0),
        text: String(c.text),
        score: Math.round(score * 100) / 100,
        citation: `[${source} :: ${String(c.title)}${c.version ? " @ " + String(c.version) : ""} :: chunk ${Number(c.chunk_index ?? 0)}]`,
      });
    }
    scored.sort((a, b) => b.score - a.score);
    return scored.slice(0, limit);
  }

  stats() { return this.db.knowledgeStats(); }
}
