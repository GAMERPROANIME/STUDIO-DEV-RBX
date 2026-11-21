"""Real tool behaviour: files, code, knowledge, plugins, automation, agents."""
from __future__ import annotations

import pytest

from omnibridge.core.permissions import PermissionDenied


def test_tool_catalogue_is_consistent(bridge):
    names = {t.name for t in bridge.registry.list()}
    assert len(names) > 60
    for required in ("system_health", "file_read", "knowledge_retrieve", "roblox_inspect_project",
                     "agent_start_task", "browser_get_active_tab", "process_run", "desktop_bridge_status"):
        assert required in names
    for tool in bridge.registry.list():
        assert tool.description, f"{tool.name} has no description"
        assert 1 <= tool.level <= 4
        for req in tool.required:
            assert req in tool.params, f"{tool.name}: required param {req} not declared"


def test_file_tools_roundtrip(bridge, workspace, run):
    created = run(bridge.call_tool("file_create", {"path": "src/client/New.client.luau", "content": "--!strict\n"}))
    assert created["ok"]
    run(bridge.call_tool("file_update", {"path": "src/client/New.client.luau", "content": "--!strict\nprint('hi')\n"}))
    read = run(bridge.call_tool("file_read", {"path": "src/client/New.client.luau"}))
    assert "print('hi')" in "\n".join(read["lines"])
    listing = run(bridge.call_tool("file_list", {"path": ".", "maxDepth": 3}))
    assert any("CombatServer" in f for f in listing["files"])
    search = run(bridge.call_tool("file_search", {"pattern": "GetService"}))
    assert search["count"] >= 1
    assert search["hits"][0]["line"] >= 1


def test_file_update_backs_up(bridge, run):
    res = run(bridge.call_tool("file_update", {"path": "README.md", "content": "# changed\n"}))
    assert res["backup"] and res["backup"].endswith(".bak")


def test_file_delete_requires_confirm_and_backup(bridge, run, workspace):
    with pytest.raises(PermissionDenied):
        run(bridge.call_tool("file_delete", {"path": "README.md"}))
    res = run(bridge.call_tool("file_delete", {"path": "README.md"}, confirmed=True))
    assert res["ok"] and res["backup"]
    assert not (workspace / "README.md").exists()


def test_file_read_rejects_binary_and_escape(bridge, workspace, run):
    (workspace / "blob.bin").write_bytes(b"\x00\x01")
    with pytest.raises(ValueError):
        run(bridge.call_tool("file_read", {"path": "blob.bin"}))
    with pytest.raises(ValueError):
        run(bridge.call_tool("file_read", {"path": "../secrets.txt"}))


def test_project_inspect_detects_rojo(bridge, run):
    info = run(bridge.call_tool("project_inspect", {}))
    assert info["type"] == "roblox-rojo"
    assert info["rojoProject"]["name"] == "Demo"


def test_code_analyze_and_review(bridge, run):
    analysis = run(bridge.call_tool("code_analyze", {"path": "src/server/CombatServer.server.luau"}))
    assert analysis["errorCount"] == 0
    review = run(bridge.call_tool("code_review", {"path": "src/server/CombatServer.server.luau"}))
    assert review["verdict"] == "ok"


def test_error_diagnose_classifies(bridge, run):
    res = run(bridge.call_tool("error_diagnose", {"message": "attempt to index nil with 'Name'"}))
    assert res["category"] == "syntax/runtime"
    assert res["suggestedFixes"]
    unknown = run(bridge.call_tool("error_diagnose", {"message": "xyzzy plugh"}))
    assert unknown["category"] == "unknown"


def test_knowledge_index_and_retrieve(bridge, run):
    run(bridge.call_tool("knowledge_index_luau", {}))
    run(bridge.call_tool("knowledge_index", {
        "source": "project-notes", "title": "Combat rules", "text":
            "Combat damage is capped at 100. Cooldowns are server authoritative. "
            "Use RemoteEvents for input, never trust the client.",
    }))
    hits = run(bridge.call_tool("knowledge_retrieve", {"query": "damage cap cooldown", "limit": 5}))
    assert hits["count"] >= 1
    assert any("Combat rules" in h["title"] for h in hits["hits"])
    assert all(h["citation"].startswith("[") for h in hits["hits"])
    stats = run(bridge.call_tool("knowledge_stats", {}))
    assert stats["sources"] >= 2


def test_memory_scopes(bridge, run):
    run(bridge.call_tool("memory_set", {"scope": "project", "key": "engine", "value": "python"}))
    got = run(bridge.call_tool("memory_get", {"scope": "project", "key": "engine"}))
    assert got["value"] == "python"
    listed = run(bridge.call_tool("memory_list", {"scope": "project"}))
    assert {"key": "engine"}.items() <= dict(listed["entries"][0]).items()


def test_plugins_list_and_diagnose(bridge, run):
    plugins = run(bridge.call_tool("plugin_list", {}))
    assert any(p["dir"] == "example-connector" for p in plugins)
    diag = run(bridge.call_tool("plugin_diagnose", {"name": "example-connector"}))
    assert diag["ok"] is True
    assert diag["missingTools"] == []


def test_automation_allowlist(bridge, run):
    actions = run(bridge.call_tool("process_list_actions", {}))
    assert "pytest" in actions["allowlistedActions"]
    with pytest.raises(PermissionDenied):
        run(bridge.call_tool("process_run", {"action": "pytest"}))
    out = run(bridge.call_tool("process_run", {"action": "python_version"}, confirmed=True))
    assert out["passed"] is True
    assert "Python" in out["stdout"]
    with pytest.raises(ValueError):
        run(bridge.call_tool("process_run", {"action": "rm -rf /"}, confirmed=True))


def test_system_health_and_diagnostics(bridge, run):
    health = run(bridge.call_tool("system_health", {}))
    assert health["toolCount"] == bridge.registry.size
    assert health["permissionLevel"] == 4
    diag = run(bridge.call_tool("system_diagnostics", {}))
    assert diag["ok"] is True, [c for c in diag["checks"] if not c["ok"]]
    tools = run(bridge.call_tool("system_list_tools", {"category": "roblox"}))
    assert all(t["category"] == "roblox" for t in tools)


def test_unknown_tool_raises(bridge, run):
    with pytest.raises(ValueError, match="Unknown tool"):
        run(bridge.call_tool("definitely_not_a_tool", {}))


def test_audit_records_every_call(bridge, run):
    run(bridge.call_tool("file_list", {"path": "."}))
    entries = run(bridge.call_tool("system_audit_log", {"limit": 10}))
    assert any(e["tool"] == "file_list" for e in entries)
