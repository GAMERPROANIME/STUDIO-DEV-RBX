"""Register the Python Native Messaging host with Chromium browsers and Firefox.

Usage:  python -m omnibridge.bridge.install [--extension-id ID]... [--uninstall] [--print]

What it does (no admin rights needed):
  * writes a launcher script in <data dir>/bridge/ that runs the Python host
  * writes the native messaging manifest JSON(s) there
  * Linux:   symlinks into ~/.config/{google-chrome,chromium,microsoft-edge}/NativeMessagingHosts
             and ~/.mozilla/native-messaging-hosts
  * macOS:   writes to ~/Library/Application Support/{Google/Chrome,Chromium,Microsoft Edge}/NativeMessagingHosts
             and ~/Library/Application Support/Mozilla/NativeMessagingHosts
  * Windows: writes HKCU\\Software\\... registry keys pointing at the manifest
"""
from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path

from ..config import load_config

HOST_NAME = "com.omnibridge.host"
DEFAULT_CHROME_EXT_IDS = ["*"]  # replaced by the user's real extension id
FIREFOX_ID = "omnibridge@local"


def _launcher(bridge_dir: Path) -> Path:
    if sys.platform == "win32":
        path = bridge_dir / "omnibridge-host.bat"
        python = Path(sys.executable)
        path.write_text(f'@echo off\r\n"{python}" -m omnibridge.bridge.native_host %*\r\n',
                        encoding="utf-8")
        return path
    path = bridge_dir / "omnibridge-host.sh"
    path.write_text(f'#!/bin/sh\nexec "{sys.executable}" -m omnibridge.bridge.native_host "$@"\n',
                    encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return path


def _manifest_paths(bridge_dir: Path) -> dict[str, Path]:
    return {
        "chromium": bridge_dir / f"{HOST_NAME}.json",
        "firefox": bridge_dir / f"{HOST_NAME}.firefox.json",
    }


def write_manifests(bridge_dir: Path, chrome_ids: list[str]) -> dict[str, Path]:
    bridge_dir.mkdir(parents=True, exist_ok=True)
    launcher = _launcher(bridge_dir)
    paths = _manifest_paths(bridge_dir)
    chromium = {"name": HOST_NAME, "description": "OMNIBRIDGE AI desktop bridge (Python)",
                "path": str(launcher), "type": "stdio",
                "allowed_origins": [f"chrome-extension://{i}/" for i in chrome_ids]}
    firefox = {"name": HOST_NAME, "description": "OMNIBRIDGE AI desktop bridge (Python)",
               "path": str(launcher), "type": "stdio",
               "allowed_extensions": [FIREFOX_ID]}
    paths["chromium"].write_text(json.dumps(chromium, indent=2), encoding="utf-8")
    paths["firefox"].write_text(json.dumps(firefox, indent=2), encoding="utf-8")
    return paths


def _install_links(paths: dict[str, Path]) -> list[str]:
    done: list[str] = []
    home = Path.home()
    if sys.platform.startswith("linux"):
        targets = [(paths["chromium"], home / ".config/google-chrome/NativeMessagingHosts"),
                   (paths["chromium"], home / ".config/chromium/NativeMessagingHosts"),
                   (paths["chromium"], home / ".config/microsoft-edge/NativeMessagingHosts"),
                   (paths["chromium"], home / ".config/BraveSoftware/Brave-Browser/NativeMessagingHosts"),
                   (paths["firefox"], home / ".mozilla/native-messaging-hosts")]
        for src, directory in targets:
            directory.mkdir(parents=True, exist_ok=True)
            dest = directory / src.name.replace(".firefox", "")
            if dest.is_symlink() or dest.exists():
                dest.unlink()
            dest.symlink_to(src)
            done.append(str(dest))
    elif sys.platform == "darwin":
        base = home / "Library/Application Support"
        targets = [(paths["chromium"], base / "Google/Chrome/NativeMessagingHosts"),
                   (paths["chromium"], base / "Chromium/NativeMessagingHosts"),
                   (paths["chromium"], base / "Microsoft Edge/NativeMessagingHosts"),
                   (paths["firefox"], base / "Mozilla/NativeMessagingHosts")]
        for src, directory in targets:
            directory.mkdir(parents=True, exist_ok=True)
            dest = directory / src.name.replace(".firefox", "")
            if dest.exists():
                dest.unlink()
            dest.symlink_to(src)
            done.append(str(dest))
    elif sys.platform == "win32":
        import winreg

        entries = [("Software\\Google\\Chrome\\NativeMessagingHosts\\", paths["chromium"]),
                   ("Software\\Chromium\\NativeMessagingHosts\\", paths["chromium"]),
                   ("Software\\Microsoft\\Edge\\NativeMessagingHosts\\", paths["chromium"]),
                   ("Software\\Mozilla\\NativeMessagingHosts\\", paths["firefox"])]
        for prefix, manifest in entries:
            key_path = prefix + HOST_NAME
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                winreg.SetValueEx(key, "", 0, winreg.REG_SZ, str(manifest))
            done.append("HKCU\\" + key_path)
    return done


def _uninstall(paths: dict[str, Path]) -> list[str]:
    removed: list[str] = []
    candidates = list((Path.home() / ".config").rglob(f"{HOST_NAME}.json")) + \
                 list((Path.home() / ".mozilla").rglob(f"{HOST_NAME}.json")) + \
                 list((Path.home() / "Library/Application Support").rglob(f"{HOST_NAME}.json"))
    for c in candidates:
        try:
            c.unlink()
            removed.append(str(c))
        except OSError:
            pass
    for p in paths.values():
        if p.exists():
            p.unlink()
            removed.append(str(p))
    return removed


def main(argv: list[str] | None = None) -> int:
    global FIREFOX_ID
    parser = argparse.ArgumentParser(prog="omnibridge-bridge-install",
                                     description="Install the OMNIBRIDGE Native Messaging host")
    parser.add_argument("--extension-id", action="append", default=[],
                        help="Chromium extension id (repeatable). Required for Chrome/Edge.")
    parser.add_argument("--firefox-id", default=FIREFOX_ID)
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--print", dest="print_only", action="store_true",
                        help="Print the generated manifests without installing")
    args = parser.parse_args(argv)

    cfg = load_config()
    bridge_dir = cfg.data_dir / "bridge"
    if args.firefox_id:
        FIREFOX_ID = args.firefox_id
    chrome_ids = args.extension_id or DEFAULT_CHROME_EXT_IDS
    paths = write_manifests(bridge_dir, chrome_ids)
    if args.print_only:
        for p in paths.values():
            print(f"# {p}\n{p.read_text(encoding='utf-8')}")
        return 0
    if args.uninstall:
        for item in _uninstall(paths):
            print(f"removed {item}")
        return 0
    if chrome_ids == ["*"]:
        print("WARNING: --extension-id not provided; Chrome/Edge will reject the connection.\n"
              "         Find the id at chrome://extensions, then re-run with --extension-id <id>.\n")
    installed = _install_links(paths)
    for item in installed:
        print(f"installed {item}")
    print(f"\nNative host '{HOST_NAME}' registered. Launcher: {paths['chromium'].parent}")
    print("Restart the browser, then click 'Connect' in the OMNIBRIDGE extension popup.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
