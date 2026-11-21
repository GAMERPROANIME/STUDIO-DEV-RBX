"""Plugin/connector manager: manifest-based connectors, validated, never over-privileged."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..core.permissions import ToolDef
from ..core.registry import Registry


def list_connectors(plugins_dir: Path) -> list[dict[str, Any]]:
    if not plugins_dir.exists():
        return []
    out = []
    for entry in sorted(plugins_dir.iterdir(), key=lambda p: p.name):
        if not entry.is_dir():
            continue
        manifest_path = entry / "manifest.json"
        if not manifest_path.exists():
            out.append({"dir": entry.name, "manifest": None, "error": "missing manifest.json"})
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if not manifest.get("name") or not manifest.get("version"):
                raise ValueError("manifest requires name and version")
            out.append({"dir": entry.name, "manifest": manifest})
        except (json.JSONDecodeError, ValueError) as e:
            out.append({"dir": entry.name, "manifest": None, "error": str(e)})
    return out


def register_plugin_tools(reg: Registry) -> None:
    async def plugin_list(args: dict, ctx) -> list[dict]:
        return list_connectors(ctx.config.plugins_dir)

    async def plugin_diagnose(args: dict, ctx) -> dict:
        connectors = list_connectors(ctx.config.plugins_dir)
        found = next((c for c in connectors
                      if (c["manifest"] or {}).get("name") == str(args["name"]) or c["dir"] == str(args["name"])), None)
        if not found:
            raise ValueError(f"Connector not found: {args['name']}")
        if not found["manifest"]:
            return {"name": str(args["name"]), "ok": False, "error": found.get("error")}
        manifest = found["manifest"]
        declared = manifest.get("tools") or []
        missing = [t for t in declared if not reg.get(t)]
        return {"name": manifest["name"], "ok": not missing, "version": manifest.get("version"),
                "enabled": manifest.get("enabled", True), "capabilities": manifest.get("capabilities", []),
                "declaredTools": declared, "missingTools": missing,
                "permissions": manifest.get("permissions", []),
                "note": "A connector never gains permissions beyond its manifest."}

    reg.register(ToolDef("plugin_list",
                         "List installed connectors/plugins with their manifests, capabilities and enabled state.",
                         {}, [], 1, "plugins", True, plugin_list))
    reg.register(ToolDef("plugin_diagnose",
                         "Diagnose a connector: validates its manifest, checks declared tools exist in the "
                         "registry, and reports permission requirements.",
                         {"name": {"type": "string"}}, ["name"], 1, "plugins", True, plugin_diagnose))
