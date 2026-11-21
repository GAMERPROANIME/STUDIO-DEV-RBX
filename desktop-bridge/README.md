# Desktop Bridge (Python)

The Desktop Bridge is a **Python** Native Messaging host. It is not a Node/JS
component any more: the browser extension talks to it over the native messaging
protocol and it forwards **tool calls only** to the local OMNIBRIDGE core.

```
browser extension ──native messaging──▶ python -m omnibridge.bridge.native_host
                                              │  (Bearer token)
                                              ▼
                                   http://127.0.0.1:8765  (Python core)
```

## Why native messaging at all?

Chrome/Firefox can start a local process and exchange length-prefixed JSON with
it. That lets the extension reach the core **without** the core having to be
reachable from a web origin, and without a second HTTP server.

## Install

```bash
# 1) find your extension id: chrome://extensions → OMNIBRIDGE → ID
python -m omnibridge.bridge.install --extension-id <your-extension-id>

# Firefox
python -m omnibridge.bridge.install --firefox-id omnibridge@local

# print the manifests without touching the system
python -m omnibridge.bridge.install --print

# remove
python -m omnibridge.bridge.install --uninstall
```

The installer writes, into `<data dir>/bridge/` (`~/.omnibridge/bridge/` by default):

- `omnibridge-host.sh` / `omnibridge-host.bat` — launcher running the Python host
- `com.omnibridge.host.json` — Chromium manifest
- `com.omnibridge.host.firefox.json` — Firefox manifest

and registers them:

| OS | Registration |
| --- | --- |
| Linux | symlinks in `~/.config/{google-chrome,chromium,microsoft-edge,BraveSoftware/Brave-Browser}/NativeMessagingHosts` and `~/.mozilla/native-messaging-hosts` |
| macOS | symlinks in `~/Library/Application Support/{Google/Chrome,Chromium,Microsoft Edge,Mozilla}/NativeMessagingHosts` |
| Windows | `HKCU\Software\{Google\Chrome,Chromium,Microsoft\Edge,Mozilla}\NativeMessagingHosts\com.omnibridge.host` |

No administrator rights are required on any platform.

## Protocol

Rectangle frames: `uint32 little-endian length` + UTF-8 JSON.

Request:

```json
{ "id": 1, "command": "status" | "tools" | "call" | "ping" | "health", "payload": { } }
```

Response:

```json
{ "id": 1, "ok": true, "result": { } }
{ "id": 1, "ok": false, "error": "permission denied: ..." }
```

`call` payload: `{ "name": "file_read", "args": { "path": "src/a.luau" }, "confirm": false }`.

Anything else — `http`, `exec`, `open` — is rejected. The host is **not** an open
proxy: the extension cannot request arbitrary URLs, files or commands.

## Autostart

If the core is not responding, the host starts it (`python -m omnibridge --transport http`)
detached, waits up to 20 s, then retries. Disable with `OMNIBRIDGE_BRIDGE_AUTOSTART=0`.

## Environment

| Variable | Default | Meaning |
| --- | --- | --- |
| `OMNIBRIDGE_URL` | `http://127.0.0.1:8765` | core endpoint |
| `OMNIBRIDGE_DATA_DIR` | `~/.omnibridge` | where `token.txt` lives |
| `OMNIBRIDGE_TOKEN` | – | overrides `token.txt` |
| `OMNIBRIDGE_BRIDGE_AUTOSTART` | `1` | start the core if needed |

## Security notes

- The host never reads page content by itself; it only forwards tool calls.
- Level-4 tools still require `confirm: true` and the core still enforces the
  configured permission level — the bridge cannot raise it.
- Every forwarded call is audited by the core (`system_audit_log`).
