import { readFileSync, existsSync, statSync } from "node:fs";
import { join, extname } from "node:path";
import type { Registry } from "../core/registry.js";
import type { ToolDef } from "../core/permissions.js";
import type { KnowledgeEngine } from "../knowledge/engine.js";
import { DOC_SOURCES, fetchText, htmlToText } from "../knowledge/sources.js";
import { LUAU_KNOWLEDGE } from "../roblox/luau.js";
import { sandboxResolve } from "../core/sandbox.js";

export function registerKnowledgeTools(reg: Registry, engine: KnowledgeEngine): void {
  const tools: ToolDef[] = [
    {
      name: "knowledge_retrieve",
      description: "Hybrid retrieval (FTS5 + TF-IDF) over the indexed knowledge base. Returns passages with citations (source, version, fetch date, reliability). Distinguishes confirmed facts from community content via the reliability field.",
      inputSchema: { type: "object", properties: { query: { type: "string" }, limit: { type: "integer", minimum: 1, maximum: 20, default: 8 } }, required: ["query"] },
      level: 1, category: "knowledge", readOnly: true,
      handler: (args) => {
        const hits = engine.retrieve(String(args.query), Number(args.limit ?? 8));
        return { query: String(args.query), count: hits.length, hits, note: "Cite hits as [source :: title @ version :: chunk N]. reliability=official means confirmed; community/web means verify." };
      },
    },
    {
      name: "knowledge_index",
      description: "Index a document into the knowledge base (chunked, FTS5 + TF-IDF). Replaces any previous document with the same source id. Secrets are redacted automatically.",
      inputSchema: { type: "object", properties: { source: { type: "string" }, title: { type: "string" }, text: { type: "string" }, version: { type: "string", default: "" }, reliability: { type: "string", enum: ["official", "community", "project", "web"], default: "project" } }, required: ["source", "title", "text"] },
      level: 3, category: "knowledge", readOnly: false,
      handler: (args) => engine.indexDocument({
        source: String(args.source), title: String(args.title), text: String(args.text),
        version: String(args.version ?? ""), reliability: (args.reliability as "official" | "community" | "project" | "web") ?? "project",
      }),
    },
    {
      name: "knowledge_index_file",
      description: "Index a workspace file (docs, .md, .txt, .luau) into the knowledge base. Useful for project documentation and decisions.",
      inputSchema: { type: "object", properties: { path: { type: "string" }, source: { type: "string", description: "Defaults to the file path" } }, required: ["path"] },
      level: 2, category: "knowledge", readOnly: false,
      handler: (args, ctx) => {
        const abs = sandboxResolve(ctx.config.workspaceRoot, String(args.path));
        if (!existsSync(abs) || !statSync(abs).isFile()) throw new Error(`Not a file: ${args.path}`);
        if (statSync(abs).size > ctx.config.maxFileBytes) throw new Error("File too large to index");
        const text = readFileSync(abs, "utf8");
        return engine.indexDocument({ source: String(args.source ?? args.path), title: String(args.path), text, reliability: "project" });
      },
    },
    {
      name: "knowledge_fetch_docs",
      description: "Fetch and index the curated official documentation sources (MCP spec, Roblox Creator Docs, Luau, Rojo…). Each document is stored with fetch date and reliability. Use sourceId to fetch one, or omit to fetch all.",
      inputSchema: { type: "object", properties: { sourceId: { type: "string" } } },
      level: 2, category: "knowledge", readOnly: false,
      handler: async (args) => {
        const list = args.sourceId ? DOC_SOURCES.filter((s) => s.id === String(args.sourceId)) : DOC_SOURCES;
        if (!list.length) throw new Error(`Unknown sourceId. Available: ${DOC_SOURCES.map((s) => s.id).join(", ")}`);
        const results: Array<Record<string, unknown>> = [];
        for (const s of list) {
          try {
            const raw = await fetchText(s.url, 25_000);
            const text = raw.trimStart().startsWith("<") ? htmlToText(raw) : raw;
            const r = engine.indexDocument({ source: s.id, title: s.title, text, version: s.version ?? "", reliability: s.reliability });
            results.push({ source: s.id, ok: true, chunks: r.chunks, fetchedAt: new Date().toISOString() });
          } catch (e) {
            results.push({ source: s.id, ok: false, error: e instanceof Error ? e.message : String(e) });
          }
        }
        return { results };
      },
    },
    {
      name: "knowledge_index_luau",
      description: "Index the built-in Luau/Roblox knowledge base (syntax, services, architecture, networking, performance). Call once at setup; idempotent.",
      inputSchema: { type: "object", properties: {} },
      level: 2, category: "knowledge", readOnly: false,
      handler: () => engine.indexDocument({ source: "luau-knowledge", title: "Luau & Roblox Knowledge Base", text: LUAU_KNOWLEDGE, reliability: "official" }),
    },
    {
      name: "memory_set",
      description: "Store a persistent memory entry. Scopes: personal (user prefs), project (decisions, conventions), temp (short-lived). Secrets are redacted. Never store passwords here.",
      inputSchema: { type: "object", properties: { scope: { type: "string", enum: ["personal", "project", "temp"], default: "project" }, key: { type: "string" }, value: { type: "string" } }, required: ["key", "value"] },
      level: 3, category: "knowledge", readOnly: false,
      handler: (args, ctx) => {
        const { redactSecrets } = require_redact();
        ctx.db.memorySet(String(args.scope ?? "project"), String(args.key), redactSecrets(String(args.value)));
        return { ok: true, scope: String(args.scope ?? "project"), key: String(args.key) };
      },
    },
    {
      name: "memory_get",
      description: "Retrieve a persistent memory entry by scope and key.",
      inputSchema: { type: "object", properties: { scope: { type: "string", enum: ["personal", "project", "temp"], default: "project" }, key: { type: "string" } }, required: ["key"] },
      level: 1, category: "knowledge", readOnly: true,
      handler: (args, ctx) => ({ scope: String(args.scope ?? "project"), key: String(args.key), value: ctx.db.memoryGet(String(args.scope ?? "project"), String(args.key)) }),
    },
    {
      name: "memory_list",
      description: "List memory entries in a scope (optionally filtered by key prefix).",
      inputSchema: { type: "object", properties: { scope: { type: "string", enum: ["personal", "project", "temp"], default: "project" }, prefix: { type: "string", default: "" } } },
      level: 1, category: "knowledge", readOnly: true,
      handler: (args, ctx) => ({ scope: String(args.scope ?? "project"), entries: ctx.db.memoryList(String(args.scope ?? "project"), String(args.prefix ?? "")) }),
    },
    {
      name: "knowledge_stats",
      description: "Knowledge base statistics: chunk count, source count, per-source breakdown.",
      inputSchema: { type: "object", properties: {} },
      level: 1, category: "knowledge", readOnly: true,
      handler: () => engine.stats(),
    },
  ];
  for (const t of tools) reg.register(t);
}

import { redactSecrets as _redact } from "../core/permissions.js";
function require_redact() { return { redactSecrets: _redact }; }
void join; void extname;
