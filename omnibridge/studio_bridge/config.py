"""Bridge configuration (env + .env), paths, tokens and limits."""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 17613


def _data_dir() -> Path:
    base = os.environ.get("OMNIBRIDGE_DATA_DIR")
    if base:
        return Path(base).expanduser().resolve()
    return Path.home() / ".omnibridge"


def _env_int(name: str, fallback: int) -> int:
    try:
        return int(os.environ.get(name, "") or fallback)
    except ValueError:
        return fallback


def _env_float(name: str, fallback: float) -> float:
    try:
        return float(os.environ.get(name, "") or fallback)
    except ValueError:
        return fallback


@dataclass
class BridgeConfig:
    """Everything the bridge needs. Every field is overridable by env/CLI."""

    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    data_dir: Path = field(default_factory=_data_dir)
    token: str = ""
    studio_command: str | None = None
    studio_args: list[str] = field(default_factory=list)
    # Discovery: Studio may still be booting when the MCP process starts.
    discovery_attempts: int = 6
    discovery_backoff_s: float = 0.8
    connect_timeout_s: float = 20.0
    call_timeout_s: float = 90.0
    startup_timeout_s: float = 8.0
    max_message_bytes: int = 512 * 1024
    max_concurrent_calls: int = 4
    permission_level: int = 3
    heartbeat_s: float = 20.0
    auth_timeout_s: float = 5.0
    max_calls_per_minute: int = 240
    allowed_tools: list[str] = field(default_factory=list)  # empty = every discovered tool
    # Origins allowed to open the WebSocket. Browser pages are NEVER allowed.
    allowed_origin_prefixes: tuple[str, ...] = (
        "chrome-extension://", "moz-extension://", "safari-web-extension://",
    )

    # ---- derived paths ----
    @property
    def token_file(self) -> Path:
        return self.data_dir / "studio_bridge_token.txt"

    @property
    def audit_file(self) -> Path:
        return self.data_dir / "studio_bridge_audit.jsonl"

    @property
    def uri(self) -> str:
        return f"ws://{self.host}:{self.port}"

    def ensure_token(self) -> str:
        if self.token:
            return self.token
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if self.token_file.exists():
            self.token = self.token_file.read_text(encoding="utf-8").strip()
        if not self.token:
            self.token = secrets.token_hex(32)
            self.token_file.write_text(self.token + "\n", encoding="utf-8")
            try:
                self.token_file.chmod(0o600)
            except OSError:
                pass
        return self.token

    def validate(self) -> None:
        if self.host not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError(
                f"Refusing to bind the Studio Bridge to '{self.host}': it must stay local "
                "(127.0.0.1). Use a tunnel if you really need remote access."
            )
        if not 1 <= self.port <= 65535:
            raise ValueError(f"Invalid port: {self.port}")
        if not 1 <= self.permission_level <= 4:
            raise ValueError("permission_level must be 1..4")


def load_config(**overrides) -> BridgeConfig:
    env_cmd = (os.environ.get("OMNIBRIDGE_STUDIO_MCP_COMMAND")
               or os.environ.get("ROBLOX_STUDIO_MCP_COMMAND") or None)
    args_raw = (os.environ.get("OMNIBRIDGE_STUDIO_MCP_ARGS")
                or os.environ.get("ROBLOX_STUDIO_MCP_ARGS") or "")
    cfg = BridgeConfig(
        host=os.environ.get("OMNIBRIDGE_BRIDGE_HOST", DEFAULT_HOST),
        port=_env_int("OMNIBRIDGE_BRIDGE_PORT", DEFAULT_PORT),
        data_dir=_data_dir(),
        token=os.environ.get("OMNIBRIDGE_BRIDGE_TOKEN") or os.environ.get("OMNIBRIDGE_TOKEN", ""),
        studio_command=env_cmd,
        studio_args=[a for a in args_raw.split() if a],
        discovery_attempts=_env_int("OMNIBRIDGE_DISCOVERY_ATTEMPTS", 6),
        discovery_backoff_s=_env_float("OMNIBRIDGE_DISCOVERY_BACKOFF_S", 0.8),
        connect_timeout_s=_env_float("OMNIBRIDGE_CONNECT_TIMEOUT_S", 20.0),
        call_timeout_s=_env_float("OMNIBRIDGE_CALL_TIMEOUT_S", 90.0),
        max_message_bytes=_env_int("OMNIBRIDGE_BRIDGE_MAX_MESSAGE_BYTES", 512 * 1024),
        max_concurrent_calls=_env_int("OMNIBRIDGE_BRIDGE_MAX_CONCURRENT", 4),
        permission_level=_env_int("OMNIBRIDGE_BRIDGE_PERMISSION_LEVEL",
                                  _env_int("OMNIBRIDGE_PERMISSION_LEVEL", 3)),
        max_calls_per_minute=_env_int("OMNIBRIDGE_BRIDGE_MAX_CALLS_PER_MIN", 240),
        allowed_tools=[t.strip() for t in os.environ.get("OMNIBRIDGE_ALLOWED_TOOLS", "").split(",") if t.strip()],
    )
    for key, value in overrides.items():
        if value is not None:
            setattr(cfg, key, value)
    cfg.ensure_token()
    return cfg
