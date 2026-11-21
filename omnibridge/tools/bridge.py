"""Desktop Bridge tools: status + installer (the host itself is a separate stdio process)."""
from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout

from ..core.permissions import ToolDef
from ..core.registry import Registry


def _host_paths(cfg) -> dict[str, bool]:
    bridge_dir = cfg.data_dir / "bridge"
    return {
        "bridgeDir": bridge_dir.exists(),
        "chromiumManifest": (bridge_dir / "com.omnibridge.host.json").exists(),
        "firefoxManifest": (bridge_dir / "com.omnibridge.host.firefox.json").exists(),
        "launcher": any((bridge_dir / n).exists() for n in
                        ("omnibridge-host.sh", "omnibridge-host.bat")),
    }


def register_bridge_tools(reg: Registry, browser_status) -> None:
    async def desktop_bridge_status(args: dict, ctx) -> dict:
        paths = _host_paths(ctx.config)
        return {
            "hostName": "com.omnibridge.host",
            "installed": all(paths[k] for k in ("chromiumManifest", "launcher")),
            "files": paths,
            "dataDir": str(ctx.config.data_dir),
            "extensionClients": browser_status().get("clients", []),
            "coreUrl": f"http://{ctx.config.http_host}:{ctx.config.http_port}",
            "note": "The native host is a Python process (omnibridge.bridge.native_host). It forwards "
                    "tool calls only — never arbitrary URLs or commands.",
        }

    async def desktop_bridge_install(args: dict, ctx) -> dict:
        from ..bridge import install as installer

        ext_ids = args.get("extensionIds") or ["*"]
        buf = io.StringIO()
        argv = ["--extension-id", ext_ids[0]] if ext_ids != ["*"] else []
        for extra in ext_ids[1:]:
            argv += ["--extension-id", extra]
        with redirect_stdout(buf):
            code = installer.main(argv)
        return {"ok": code == 0, "exitCode": code, "extensionIds": ext_ids,
                "output": buf.getvalue(), "platform": sys.platform,
                "next": "Restart the browser, then use the extension popup → Connect."}

    reg.register(ToolDef("desktop_bridge_status",
                         "Status of the Desktop Bridge (Native Messaging host): manifest/launcher present, "
                         "data dir, connected extension clients, core URL.",
                         {}, [], 1, "bridge", True, desktop_bridge_status))
    reg.register(ToolDef("desktop_bridge_install",
                         "Install/refresh the Python Native Messaging host for Chrome, Edge, Chromium, Brave "
                         "and Firefox. Pass the Chromium extension id(s) so the browser accepts the host.",
                         {"extensionIds": {"type": "array", "items": {"type": "string"}, "default": []}},
                         [], 3, "bridge", False, desktop_bridge_install))
