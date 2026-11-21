"""Hybrid retrieval over SQLite FTS5 + TF-IDF re-ranking, with citations."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

from ..core.db import Db
from ..core.permissions import redact_secrets

CHUNK_SIZE = 1200
OVERLAP = 200


@dataclass
class KnowledgeHit:
    id: int
    source: str
    title: str
    version: str
    fetched_at: str
    reliability: str
    chunk_index: int
    text: str
    score: float
    citation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "source": self.source, "title": self.title, "version": self.version,
            "fetchedAt": self.fetched_at, "reliability": self.reliability,
            "chunkIndex": self.chunk_index, "text": self.text, "score": self.score,
            "citation": self.citation,
        }


def chunk_text(text: str) -> list[str]:
    clean = text.replace("\r\n", "\n").strip()
    if not clean:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(clean):
        end = min(start + CHUNK_SIZE, len(clean))
        if end < len(clean):
            brk = clean.rfind("\n", start, end)
            if brk > start + CHUNK_SIZE * 0.4:
                end = brk
        chunks.append(clean[start:end].strip())
        if end >= len(clean):
            break
        start = max(end - OVERLAP, start + 1)
    return [c for c in chunks if len(c) > 20]


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_]{2,}", text.lower())


def _tfidf_scores(query: str, chunks: list[dict[str, Any]]) -> dict[int, float]:
    q_tokens = _tokenize(query)
    scores: dict[int, float] = {}
    if not q_tokens or not chunks:
        return scores
    df: dict[str, int] = {}
    docs = [(int(c["id"]), _tokenize(str(c["text"]))) for c in chunks]
    for _, tokens in docs:
        for t in set(tokens):
            df[t] = df.get(t, 0) + 1
    n = len(docs)
    for doc_id, tokens in docs:
        tf: dict[str, int] = {}
        for t in tokens:
            tf[t] = tf.get(t, 0) + 1
        s = 0.0
        for q in q_tokens:
            f = tf.get(q)
            if not f:
                continue
            idf = math.log(1 + n / (1 + df.get(q, 0)))
            s += (1 + math.log(f)) * idf
        if s > 0:
            scores[doc_id] = s
    return scores


class KnowledgeEngine:
    def __init__(self, db: Db):
        self._db = db

    def index_document(self, source: str, title: str, text: str, version: str = "",
                       reliability: str = "project") -> dict[str, int]:
        self._db.knowledge_clear_source(source)
        chunks = chunk_text(redact_secrets(text))
        for i, c in enumerate(chunks):
            self._db.knowledge_insert(source, title, version, reliability, i, c)
        return {"chunks": len(chunks)}

    def retrieve(self, query: str, limit: int = 8) -> list[KnowledgeHit]:
        fts_query = " OR ".join(_tokenize(query))
        fts_hits = self._db.knowledge_search_fts(fts_query, max(limit * 4, 40)) if fts_query else []
        all_chunks = self._db.knowledge_all_chunks(20000)
        tfidf = _tfidf_scores(query, all_chunks)
        by_id: dict[int, dict[str, Any]] = {int(c["id"]): c for c in all_chunks}
        for h in fts_hits:
            by_id[int(h["id"])] = h
        scored: list[KnowledgeHit] = []
        for cid, c in by_id.items():
            score = tfidf.get(cid, 0.0)
            if score <= 0:
                continue
            source = str(c["source"])
            version = str(c.get("version") or "")
            scored.append(KnowledgeHit(
                id=cid, source=source, title=str(c["title"]), version=version,
                fetched_at=str(c.get("fetched_at") or ""), reliability=str(c.get("reliability") or "community"),
                chunk_index=int(c.get("chunk_index") or 0), text=str(c["text"]),
                score=round(score, 2),
                citation=f"[{source} :: {c['title']}{' @ ' + version if version else ''} :: chunk {int(c.get('chunk_index') or 0)}]",
            ))
        scored.sort(key=lambda h: h.score, reverse=True)
        return scored[:limit]

    def stats(self) -> dict[str, Any]:
        return self._db.knowledge_stats()
