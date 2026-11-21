"""Regenerate docs/TOOLS.md from the live tool registry.

Usage:  python tools/gen_tool_docs.py
Docs must never drift from the code: this script reads the real registry.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from omnibridge.config import load_config  # noqa: E402
from omnibridge.core.app import OmniBridge  # noqa: E402
from omnibridge.mcp_server import effective_params  # noqa: E402

ORDER = ["system", "files", "project", "code", "knowledge", "web", "roblox",
         "browser", "bridge", "agent", "plugins", "automation"]


def render(bridge: OmniBridge) -> str:
    cats = bridge.registry.categories()
    lines = [
        "# Catalogue des outils (généré depuis le registre)",
        "",
        f"**{bridge.registry.size} outils réels**, enregistrés dans `omnibridge/core/registry.py` et exposés par le",
        "serveur MCP Python. Ce fichier est généré depuis le code : `python tools/gen_tool_docs.py`.",
        "",
        "Niveaux : **L1** lecture · **L2** assistance (sauvegarde + audit) · **L3** automatisation contrôlée · "
        "**L4** sensible (`confirm=true` obligatoire).",
        "",
    ]
    for cat in ORDER + [c for c in sorted(cats) if c not in ORDER]:
        if cat not in cats:
            continue
        lines += [f"## {cat} ({len(cats[cat])})", "",
                  "| Outil | Niv. | R/W | Description | Paramètres |",
                  "| --- | --- | --- | --- | --- |"]
        for name in cats[cat]:
            tool = bridge.registry.get(name)
            params = effective_params(tool)
            ps = ", ".join(f"`{k}`{'' if k in tool.required else '?'}" for k in params) or "—"
            desc = tool.description.replace("|", "\\|").replace("\n", " ")
            lines.append(f"| `{name}` | {tool.level} | {'R' if tool.read_only else 'W'} | {desc} | {ps} |")
        lines.append("")
    lines += [
        "---",
        "",
        "`?` = paramètre optionnel. Les schémas JSON complets sont exposés par MCP (`tools/list`)",
        "et visibles dans le dashboard → MCP Explorer.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    bridge = OmniBridge(load_config())
    out = ROOT / "docs" / "TOOLS.md"
    out.write_text(render(bridge), encoding="utf-8")
    print(f"wrote {out} ({bridge.registry.size} tools)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
