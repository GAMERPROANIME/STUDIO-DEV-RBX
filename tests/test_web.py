"""Web intelligence: parsing, host allow-list, untrusted-content handling (no live network)."""
from __future__ import annotations

import pytest

from omnibridge.tools import web as web_tools

DDG_HTML = """
<html><body>
  <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fcreate.roblox.com%2Fdocs">Roblox Docs</a>
  <a class="result__snippet">Official Roblox Creator documentation</a>
  <a class="result__a" href="https://luau.org/">Luau</a>
  <a class="result__snippet">Luau language reference</a>
</body></html>
"""


def test_duckduckgo_parser_decodes_redirects():
    results = web_tools._parse_duckduckgo(DDG_HTML)
    assert results[0]["title"] == "Roblox Docs"
    assert results[0]["url"] == "https://create.roblox.com/docs"
    assert results[1]["url"] == "https://luau.org/"
    assert "Creator" in results[0]["snippet"]


def test_host_allowlist():
    web_tools._check_host("https://create.roblox.com/docs", ["roblox.com"])
    with pytest.raises(ValueError, match="not in OMNIBRIDGE_WEB_ALLOWED_HOSTS"):
        web_tools._check_host("https://evil.example.com/", ["roblox.com"])


def test_web_open_rejects_non_http(bridge, run):
    with pytest.raises(ValueError):
        run(bridge.call_tool("web_open", {"url": "file:///etc/passwd"}))
    with pytest.raises(ValueError):
        run(bridge.call_tool("web_open", {"url": "javascript:alert(1)"}))


def test_web_search_parses_without_network(bridge, run, monkeypatch):
    async def fake_fetch(url, timeout_s=20.0):
        assert "duckduckgo" in url
        return DDG_HTML

    monkeypatch.setattr(web_tools, "fetch_text", fake_fetch)
    res = run(bridge.call_tool("web_search", {"query": "roblox mcp", "maxResults": 2}))
    assert res["count"] == 2
    assert res["results"][0]["url"].startswith("https://")
    assert "UNTRUSTED" in res["warning"]


def test_web_open_returns_untrusted_marker(bridge, run, monkeypatch):
    async def fake_fetch(url, timeout_s=20.0):
        return "<html><body><h1>Title</h1><script>evil()</script><p>Body text</p></body></html>"

    monkeypatch.setattr(web_tools, "fetch_text", fake_fetch)
    res = run(bridge.call_tool("web_open", {"url": "https://example.com/doc"}))
    assert "Body text" in res["text"]
    assert "evil()" not in res["text"]  # scripts stripped
    assert "UNTRUSTED" in res["warning"]


def test_web_extract_structure(bridge, run, monkeypatch):
    async def fake_fetch(url, timeout_s=20.0):
        return ('<html><body><h1>A</h1><h2>B</h2>'
                '<a href="https://example.com/x">link</a><pre><code>local x = 1</code></pre>'
                "</body></html>")

    monkeypatch.setattr(web_tools, "fetch_text", fake_fetch)
    res = run(bridge.call_tool("web_extract", {"url": "https://example.com/"}))
    assert [h["text"] for h in res["headings"]] == ["A", "B"]
    assert res["links"][0]["href"] == "https://example.com/x"
    assert "local x = 1" in res["codeBlocks"][0]


def test_allowed_hosts_block_fetch(bridge, cfg, run):
    cfg.web_allowed_hosts = ["roblox.com"]
    with pytest.raises(ValueError):
        run(bridge.call_tool("web_open", {"url": "https://example.com/"}))


def test_documentation_search_uses_local_index(bridge, run):
    run(bridge.call_tool("knowledge_index_luau", {}))
    res = run(bridge.call_tool("documentation_search", {"query": "luau", "limit": 3}))
    assert res["localHits"]["count"] >= 1
    assert res["curatedSources"]


def test_curated_sources_are_official():
    from omnibridge.knowledge.sources import DOC_SOURCES

    assert len(DOC_SOURCES) >= 5
    for source in DOC_SOURCES:
        assert source["url"].startswith("https://")
        assert source["reliability"] in ("official", "community")
        assert source["id"] and source["title"]
