"""Configuration loading (environment + .env file)."""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path


def _env_int(name: str, fallback: int) -> int:
    v = os.environ.get(name)
    if not v:
        return fallback
    try:
        return int(v)
    except ValueError:
        return fallback


def _load_dotenv(root: Path) -> None:
    p = root / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        os.environ.setdefault(k, v)


def default_data_dir() -> Path:
    base = os.environ.get("OMNIBRIDGE_DATA_DIR")
    if base:
        return Path(base).expanduser().resolve()
    return Path.home() / ".omnibridge"


@dataclass
class Config:
    transport: str = "both"  # stdio | http | both
    http_host: str = "127.0.0.1"
    http_port: int = 8765
    token: str = ""
    permission_level: int = 2  # 1..4
    workspace_root: Path = field(default_factory=Path.cwd)
    data_dir: Path = field(default_factory=default_data_dir)
    max_file_bytes: int = 2_000_000
    agent_max_steps: int = 40
    agent_max_retries: int = 2
    agent_step_timeout_s: float = 120.0
    roblox_studio_mcp_command: str | None = None
    roblox_studio_mcp_args: list[str] = field(default_factory=list)
    web_allowed_hosts: list[str] = field(default_factory=list)
    dashboard_dir: Path = field(default_factory=lambda: Path.cwd() / "dashboard")
    plugins_dir: Path = field(default_factory=lambda: Path.cwd() / "plugins")
    require_token: bool = True

    def ensure_token(self) -> str:
        if self.token:
            return self.token
        token_file = self.data_dir / "token.txt"
        if token_file.exists():
            self.token = token_file.read_text(encoding="utf-8").strip()
        if not self.token:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self.token = secrets.token_hex(32)
            token_file.write_text(self.token + "\n", encoding="utf-8")
            token_file.chmod(0o600)
        return self.token


def load_config(**overrides) -> Config:
    root = Path.cwd().resolve()
    _load_dotenv(root)
    level = _env_int("OMNIBRIDGE_PERMISSION_LEVEL", 2)
    cfg = Config(
        transport=os.environ.get("OMNIBRIDGE_TRANSPORT", "both"),
        http_host=os.environ.get("OMNIBRIDGE_HTTP_HOST", "127.0.0.1"),
        http_port=_env_int("OMNIBRIDGE_HTTP_PORT", 8765),
        token=os.environ.get("OMNIBRIDGE_TOKEN", ""),
        permission_level=level if 1 <= level <= 4 else 2,
        workspace_root=Path(os.environ.get("OMNIBRIDGE_WORKSPACE", str(root))).expanduser().resolve(),
        data_dir=default_data_dir(),
        max_file_bytes=_env_int("OMNIBRIDGE_MAX_FILE_BYTES", 2_000_000),
        agent_max_steps=_env_int("OMNIBRIDGE_AGENT_MAX_STEPS", 40),
        agent_max_retries=_env_int("OMNIBRIDGE_AGENT_MAX_RETRIES", 2),
        agent_step_timeout_s=float(_env_int("OMNIBRIDGE_AGENT_STEP_TIMEOUT_MS", 120_000)) / 1000.0,
        roblox_studio_mcp_command=os.environ.get("ROBLOX_STUDIO_MCP_COMMAND") or None,
        roblox_studio_mcp_args=(os.environ.get("ROBLOX_STUDIO_MCP_ARGS", "").split() or []),
        web_allowed_hosts=[h.strip() for h in os.environ.get("OMNIBRIDGE_WEB_ALLOWED_HOSTS", "").split(",") if h.strip()],
        dashboard_dir=Path(os.environ.get("OMNIBRIDGE_DASHBOARD_DIR", str(root / "dashboard"))).expanduser().resolve(),
        plugins_dir=Path(os.environ.get("OMNIBRIDGE_PLUGINS_DIR", str(root / "plugins"))).expanduser().resolve(),
        require_token=os.environ.get("OMNIBRIDGE_REQUIRE_TOKEN", "1") != "0",
    )
    for k, v in overrides.items():
        setattr(cfg, k, v)
    # The token exists as soon as the config is loaded, so HTTP/MCP auth is always ready.
    if cfg.require_token:
        cfg.ensure_token()
    return cfg
