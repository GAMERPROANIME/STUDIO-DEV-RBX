"""Luau static analysis + embedded knowledge base."""
from __future__ import annotations

from omnibridge.roblox.luau import LUAU_KNOWLEDGE, ROBLOX_SERVICES, analyze_luau


def test_clean_script_has_no_errors():
    src = '--!strict\nlocal Players = game:GetService("Players")\nprint(Players)\n'
    issues = analyze_luau(src, "a.luau")
    assert [i for i in issues if i.severity == "error"] == []


def test_unknown_service_is_error():
    issues = analyze_luau('local X = game:GetService("NotARealService")\n', "a.luau")
    assert any(i.severity == "error" and "NotARealService" in i.message for i in issues)


def test_deprecated_globals_flagged():
    issues = analyze_luau("wait(1)\nspawn(function() end)\n", "a.luau")
    messages = " ".join(i.message for i in issues)
    assert "wait" in messages and "spawn" in messages
    assert any(i.severity == "warning" for i in issues)


def test_unbalanced_delimiters():
    issues = analyze_luau("local t = {\n  1, 2\n", "a.luau")
    assert any(i.severity == "error" for i in issues)


def test_missing_strict_mode_is_reported():
    issues = analyze_luau("print('x')\n", "a.luau")
    assert any("strict" in i.message.lower() for i in issues)


def test_knowledge_base_covers_core_services():
    assert "DataStoreService" in ROBLOX_SERVICES
    for token in ("RemoteEvent", "GetService", "task.wait", "UpdateAsync"):
        assert token in LUAU_KNOWLEDGE
