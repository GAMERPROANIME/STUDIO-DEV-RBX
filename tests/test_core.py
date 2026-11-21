"""Core primitives: sandbox, permissions, validation, database, logger."""
from __future__ import annotations

from pathlib import Path

import pytest

from omnibridge.core.db import Db
from omnibridge.core.permissions import PermissionDenied, ToolDef, check_permission, redact_secrets
from omnibridge.core.sandbox import SandboxError, sandbox_resolve
from omnibridge.core.validation import ValidationError, validate_args


def test_sandbox_allows_workspace_paths(workspace: Path):
    assert sandbox_resolve(workspace, "src/server/CombatServer.server.luau").is_file()
    assert sandbox_resolve(workspace, ".") == workspace.resolve()


@pytest.mark.parametrize("bad", ["../outside.txt", "../../etc/passwd", "/etc/passwd", "src/../../../outside.txt"])
def test_sandbox_blocks_escapes(workspace: Path, bad: str):
    with pytest.raises(SandboxError):
        sandbox_resolve(workspace, bad)


def test_sandbox_blocks_symlink_escape(workspace: Path, tmp_path: Path):
    secret = tmp_path / "secret.txt"
    secret.write_text("top secret", encoding="utf-8")
    link = workspace / "link.txt"
    try:
        link.symlink_to(secret)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(SandboxError):
        sandbox_resolve(workspace, "link.txt")


def test_permission_levels(cfg):
    read = ToolDef("t1", "read", level=1)
    write = ToolDef("t3", "write", level=3)
    sensitive = ToolDef("t4", "sensitive", level=4)

    cfg.permission_level = 2
    check_permission(cfg, read, {})
    with pytest.raises(PermissionDenied):
        check_permission(cfg, write, {})
    with pytest.raises(PermissionDenied):
        check_permission(cfg, sensitive, {})

    cfg.permission_level = 4
    with pytest.raises(PermissionDenied):
        check_permission(cfg, sensitive, {})
    check_permission(cfg, sensitive, {"confirm": True})


def test_redact_secrets():
    text = 'api_key = "abc123" and password: hunter2 and ghp_abcdefghijklmnopqrstuvwxyz123456'
    out = redact_secrets(text)
    assert "abc123" not in out
    assert "hunter2" not in out
    assert "ghp_" not in out


def test_validate_args_defaults_and_types():
    tool = ToolDef("demo", "demo", params={
        "path": {"type": "string"},
        "limit": {"type": "integer", "default": 5, "minimum": 1, "maximum": 10},
        "flag": {"type": "boolean"},
    }, required=["path"])
    assert validate_args(tool, {"path": "a"}) == {"path": "a", "limit": 5}
    assert validate_args(tool, {"path": "a", "limit": "7"})["limit"] == 7
    assert validate_args(tool, {"path": "a", "flag": "true"})["flag"] is True
    with pytest.raises(ValidationError):
        validate_args(tool, {"limit": 3})
    with pytest.raises(ValidationError):
        validate_args(tool, {"path": "a", "limit": 99})


def test_db_memory_roundtrip(cfg):
    db = Db(cfg)
    db.memory_set("project", "stack", "python")
    db.memory_set("personal", "editor", "vim")
    assert db.memory_get("project", "stack") == "python"
    assert db.memory_get("personal", "missing") is None
    keys = [e["key"] for e in db.memory_list("personal")]
    assert keys == ["editor"]
    db.close()


def test_db_tasks_and_audit(cfg):
    db = Db(cfg)
    db.task_upsert("task-1", "goal", "running", {"steps": []}, {})
    assert db.task_get("task-1")["status"] == "running"
    assert db.task_list()[0]["id"] == "task-1"
    cid = db.checkpoint_add("task-1", 1, {"done": ["s1"]})
    assert cid >= 1
    assert db.checkpoint_latest("task-1")["snapshot"]["done"] == ["s1"]
    db.audit("file_read", 1, True)
    db.audit("process_run", 4, False, "denied")
    recent = db.audit_recent(2)
    assert recent[0]["tool"] == "process_run" and recent[0]["ok"] == 0
    db.close()
