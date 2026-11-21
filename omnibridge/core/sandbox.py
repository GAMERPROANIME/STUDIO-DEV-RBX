"""Path sandbox: file operations must stay inside the workspace root."""
from __future__ import annotations

from pathlib import Path


class SandboxError(ValueError):
    pass


def sandbox_resolve(root: Path, user_path: str) -> Path:
    """Resolve user_path inside root, rejecting escapes (incl. symlinks)."""
    abs_root = root.resolve()
    candidate = Path(user_path)
    if not candidate.is_absolute():
        candidate = abs_root / candidate
    candidate = Path(candidate).resolve() if candidate.exists() else _resolve_lexical(candidate)
    try:
        candidate.relative_to(abs_root)
    except ValueError:
        raise SandboxError(f"Path escapes workspace sandbox: {user_path}") from None
    # Symlink check for existing paths.
    if candidate.exists():
        real = candidate.resolve()
        try:
            real.relative_to(abs_root)
        except ValueError:
            raise SandboxError(f"Path escapes workspace sandbox via symlink: {user_path}") from None
        return real
    return candidate


def _resolve_lexical(p: Path) -> Path:
    """Lexical absolute resolution without requiring existence (py3.11-safe)."""
    parts: list[str] = []
    for part in p.parts:
        if part in ("", "."):
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    anchor = p.anchor or "/"
    return Path(anchor, *parts)


def is_inside(root: Path, p: Path) -> bool:
    try:
        p.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False
