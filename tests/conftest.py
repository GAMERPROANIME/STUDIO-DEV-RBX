"""Shared pytest fixtures: isolated workspace + data dir for every test."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from omnibridge.config import Config  # noqa: E402
from omnibridge.core.app import OmniBridge  # noqa: E402


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "README.md").write_text("# demo project\n", encoding="utf-8")
    (ws / "src" / "server").mkdir(parents=True)
    (ws / "src" / "server" / "CombatServer.server.luau").write_text(
        '--!strict\nlocal Players = game:GetService("Players")\n'
        "local function onPlayerAdded(player: Player): ()\n\tprint(player.Name)\nend\n"
        "Players.PlayerAdded:Connect(onPlayerAdded)\n",
        encoding="utf-8",
    )
    (ws / "project.json").write_text(
        '{"name": "Demo", "tree": {"$className": "DataModel", '
        '"ServerScriptService": {"$path": "src/server"}}}',
        encoding="utf-8",
    )
    return ws


@pytest.fixture
def cfg(workspace: Path, tmp_path: Path) -> Config:
    c = Config(
        workspace_root=workspace,
        data_dir=tmp_path / "data",
        dashboard_dir=ROOT / "dashboard",
        plugins_dir=ROOT / "plugins",
        permission_level=4,
        require_token=True,
        agent_step_timeout_s=30.0,
    )
    c.ensure_token()
    return c


@pytest.fixture
def bridge(cfg: Config) -> OmniBridge:
    return OmniBridge(cfg)


@pytest.fixture
def run():
    """Run a coroutine in a fresh event loop (tests stay synchronous and readable)."""

    def _run(coro):
        return asyncio.run(coro)

    return _run
