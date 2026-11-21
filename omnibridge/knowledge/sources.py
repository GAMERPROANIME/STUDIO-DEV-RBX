"""Curated documentation sources + fetching (httpx + BeautifulSoup)."""
from __future__ import annotations

import httpx
from bs4 import BeautifulSoup

DOC_SOURCES: list[dict] = [
    {"id": "mcp-spec", "title": "Model Context Protocol Specification",
     "url": "https://modelcontextprotocol.io/specification/2025-11-25", "reliability": "official", "version": "2025-11-25"},
    {"id": "mcp-python-sdk", "title": "MCP Python SDK",
     "url": "https://github.com/modelcontextprotocol/python-sdk", "reliability": "official"},
    {"id": "roblox-creator-docs", "title": "Roblox Creator Documentation",
     "url": "https://create.roblox.com/docs", "reliability": "official"},
    {"id": "roblox-studio-mcp", "title": "Roblox Studio MCP Server docs",
     "url": "https://create.roblox.com/docs/studio/mcp", "reliability": "official"},
    {"id": "luau-docs", "title": "Luau Language Documentation",
     "url": "https://luau.org/syntax", "reliability": "official"},
    {"id": "roblox-open-cloud", "title": "Roblox Open Cloud API",
     "url": "https://create.roblox.com/docs/open-cloud", "reliability": "official"},
    {"id": "rojo-docs", "title": "Rojo Documentation",
     "url": "https://rojo.space/docs/", "reliability": "community"},
]


async def fetch_text(url: str, timeout_s: float = 20.0, max_bytes: int = 1_500_000) -> str:
    async with httpx.AsyncClient(timeout=timeout_s, follow_redirects=True,
                                 headers={"User-Agent": "OMNIBRIDGE-AI/1.0 (+local knowledge indexer)",
                                          "Accept": "text/html,text/plain,*/*"}) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content[:max_bytes].decode("utf-8", errors="replace")


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    for h in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        h.insert_before("\n\n## ")
        h.insert_after("\n")
    for li in soup.find_all("li"):
        li.insert_before("\n- ")
    for p in soup.find_all("p"):
        p.insert_before("\n\n")
    text = soup.get_text(" ")
    lines = [" ".join(l.split()) for l in text.splitlines()]
    out = "\n".join(lines)
    while "\n\n\n" in out:
        out = out.replace("\n\n\n", "\n\n")
    return out.strip()
