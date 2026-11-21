# Browser extension

MV3 extension (`extension/`) — Chromium (Chrome/Edge/Brave) + Firefox-compatible.

## Install
1. Start OMNIBRIDGE: `npm start`.
2. Chrome: `chrome://extensions` → Developer mode → **Load unpacked** → select `extension/`.
   Firefox: `about:debugging` → This Firefox → Load Temporary Add-on → `extension/manifest.json`.
3. Click the extension icon, paste the token from `~/.omnibridge/token.txt`, choose a mode, Connect.
4. `browser_status` should report `connected: true`.

## Modes
- **manual**: user chooses what to share (selection, explicit actions).
- **contextual**: active-tab context on demand.
- **developer**: technical page info (links, structure).
- **research**: document-oriented extraction.

## How it works
The extension long-polls `http://127.0.0.1:8765/bridge/poll` for commands queued by
`browser_*` MCP tools, executes them in the active tab (content script), and posts
results to `/bridge/result`. Native Messaging to the Desktop Bridge host
(`desktop-bridge/`) is supported as a fallback channel.

## Privacy
The extension never reads cookies, passwords, or form fields. It only extracts
page text, selection, links and screenshots — and only when a tool requests it
or the user acts. See `extension/content.js`.
