"""Knowledge + memory tools."""
from __future__ import annotations

from ..core.permissions import ToolDef, redact_secrets
from ..core.registry import Registry
from ..core.sandbox import sandbox_resolve
from ..knowledge.engine import KnowledgeEngine
from ..knowledge.sources import DOC_SOURCES, fetch_text, html_to_text
from ..roblox.luau import LUAU_KNOWLEDGE


def register_knowledge_tools(reg: Registry, engine: KnowledgeEngine) -> None:
    async def retrieve(args: dict, ctx) -> dict:
        hits = engine.retrieve(str(args["query"]), int(args.get("limit", 8)))
        return {"query": str(args["query"]), "count": len(hits),
                "hits": [h.to_dict() for h in hits],
                "note": "Cite hits as [source :: title @ version :: chunk N]. reliability=official means confirmed; "
                        "community/web means verify."}

    async def index(args: dict, ctx) -> dict:
        return engine.index_document(
            source=str(args["source"]), title=str(args["title"]), text=str(args["text"]),
            version=str(args.get("version", "")), reliability=str(args.get("reliability", "project")))

    async def index_file(args: dict, ctx) -> dict:
        abs_path = sandbox_resolve(ctx.config.workspace_root, str(args["path"]))
        if not abs_path.is_file():
            raise ValueError(f"Not a file: {args['path']}")
        if abs_path.stat().st_size > ctx.config.max_file_bytes:
            raise ValueError("File too large to index")
        return engine.index_document(source=str(args.get("source") or args["path"]),
                                     title=str(args["path"]),
                                     text=abs_path.read_text(encoding="utf-8"), reliability="project")

    async def fetch_docs(args: dict, ctx) -> dict:
        selected = [s for s in DOC_SOURCES if s["id"] == str(args["sourceId"])] if args.get("sourceId") else DOC_SOURCES
        if not selected:
            raise ValueError(f"Unknown sourceId. Available: {', '.join(s['id'] for s in DOC_SOURCES)}")
        results = []
        for s in selected:
            try:
                raw = await fetch_text(s["url"], 25.0)
                text = html_to_text(raw) if raw.lstrip().startswith("<") else raw
                r = engine.index_document(source=s["id"], title=s["title"], text=text,
                                          version=s.get("version", ""), reliability=s["reliability"])
                results.append({"source": s["id"], "ok": True, "chunks": r["chunks"]})
            except Exception as e:  # noqa: BLE001
                results.append({"source": s["id"], "ok": False, "error": str(e)})
        return {"results": results}

    async def index_luau(args: dict, ctx) -> dict:
        return engine.index_document(source="luau-knowledge", title="Luau & Roblox Knowledge Base",
                                     text=LUAU_KNOWLEDGE, reliability="official")

    async def memory_set(args: dict, ctx) -> dict:
        scope = str(args.get("scope", "project"))
        ctx.db.memory_set(scope, str(args["key"]), redact_secrets(str(args["value"])))
        return {"ok": True, "scope": scope, "key": str(args["key"])}

    async def memory_get(args: dict, ctx) -> dict:
        scope = str(args.get("scope", "project"))
        return {"scope": scope, "key": str(args["key"]), "value": ctx.db.memory_get(scope, str(args["key"]))}

    async def memory_list(args: dict, ctx) -> dict:
        scope = str(args.get("scope", "project"))
        return {"scope": scope, "entries": ctx.db.memory_list(scope, str(args.get("prefix", "")))}

    async def stats(args: dict, ctx) -> dict:
        return engine.stats()

    reg.register(ToolDef("knowledge_retrieve",
                         "Hybrid retrieval (FTS5 + TF-IDF) over the indexed knowledge base. Returns passages "
                         "with citations (source, version, fetch date, reliability).",
                         {"query": {"type": "string"},
                          "limit": {"type": "integer", "default": 8, "minimum": 1, "maximum": 20}},
                         ["query"], 1, "knowledge", True, retrieve))
    reg.register(ToolDef("knowledge_index",
                         "Index a document into the knowledge base (chunked, FTS5 + TF-IDF). Replaces any "
                         "previous document with the same source id. Secrets are redacted automatically.",
                         {"source": {"type": "string"}, "title": {"type": "string"}, "text": {"type": "string"},
                          "version": {"type": "string", "default": ""},
                          "reliability": {"type": "string", "default": "project",
                                          "enum": ["official", "community", "project", "web"]}},
                         ["source", "title", "text"], 3, "knowledge", False, index))
    reg.register(ToolDef("knowledge_index_file",
                         "Index a workspace file (docs, .md, .txt, .luau) into the knowledge base.",
                         {"path": {"type": "string"},
                          "source": {"type": "string", "description": "Defaults to the file path"}},
                         ["path"], 2, "knowledge", False, index_file))
    reg.register(ToolDef("knowledge_fetch_docs",
                         "Fetch and index the curated official documentation sources (MCP spec, Roblox Creator "
                         "Docs, Luau, Rojo…). Stored with fetch date and reliability.",
                         {"sourceId": {"type": "string"}}, [], 2, "knowledge", False, fetch_docs))
    reg.register(ToolDef("knowledge_index_luau",
                         "Index the built-in Luau/Roblox knowledge base. Call once at setup; idempotent.",
                         {}, [], 2, "knowledge", False, index_luau))
    reg.register(ToolDef("memory_set",
                         "Store a persistent memory entry. Scopes: personal, project, temp. Secrets are "
                         "redacted. Never store passwords here.",
                         {"scope": {"type": "string", "default": "project", "enum": ["personal", "project", "temp"]},
                          "key": {"type": "string"}, "value": {"type": "string"}},
                         ["key", "value"], 3, "knowledge", False, memory_set))
    reg.register(ToolDef("memory_get",
                         "Retrieve a persistent memory entry by scope and key.",
                         {"scope": {"type": "string", "default": "project", "enum": ["personal", "project", "temp"]},
                          "key": {"type": "string"}},
                         ["key"], 1, "knowledge", True, memory_get))
    reg.register(ToolDef("memory_list",
                         "List memory entries in a scope (optionally filtered by key prefix).",
                         {"scope": {"type": "string", "default": "project", "enum": ["personal", "project", "temp"]},
                          "prefix": {"type": "string", "default": ""}},
                         [], 1, "knowledge", True, memory_list))
    reg.register(ToolDef("knowledge_stats",
                         "Knowledge base statistics: chunk count, source count, per-source breakdown.",
                         {}, [], 1, "knowledge", True, stats))
