# Connecting AI clients

OMNIBRIDGE speaks MCP over **stdio** (local clients) and **Streamable HTTP** (remote/localhost clients).

## 1. Start the server
```bash
npm install
npm run build
npm start            # stdio + HTTP on 127.0.0.1:8765
```
Token: `~/.omnibridge/token.txt` (auto-generated, mode 0600).

## 2. Claude Code
```bash
claude mcp add omnibridge -- node /absolute/path/to/STUDIO-DEV-RBX/dist/index.js
# or .mcp.json at project root:
# { "mcpServers": { "omnibridge": { "command": "node", "args": ["/abs/path/dist/index.js"] } } }
```

## 3. Claude Desktop / Cursor / VS Code (stdio)
Add to `claude_desktop_config.json` (or Cursor/VS Code MCP config):
```json
{
  "mcpServers": {
    "omnibridge": {
      "command": "node",
      "args": ["/absolute/path/to/STUDIO-DEV-RBX/dist/index.js"]
    }
  }
}
```
VS Code (`.vscode/mcp.json`): same shape under `"servers"`.

## 4. Streamable HTTP clients (ChatGPT/Codex, custom)
- Endpoint: `http://127.0.0.1:8765/mcp`
- Header: `Authorization: Bearer <token from ~/.omnibridge/token.txt>`
- The server is stateful (MCP sessions). Start with `OMNIBRIDGE_TRANSPORT=http`.

## 5. Roblox Studio (official MCP)
1. Open a place in Roblox Studio.
2. Assistant → Settings → MCP Servers → enable **Enable Studio as MCP server**.
3. Set `ROBLOX_STUDIO_MCP_COMMAND` to the StudioMCP binary
   (Windows: `%LOCALAPPDATA%\Roblox\mcp.bat`, macOS: `StudioMCP` inside `RobloxStudio.app`).
4. Restart OMNIBRIDGE, then call `roblox_list_studios` — it should name your open place.
   OMNIBRIDGE proxies Roblox's own tools; it never duplicates them.
5. Without Studio: use Rojo projects — `roblox_inspect_project`, `roblox_read_script`, `roblox_edit_scripts` work on disk.

## 6. Browser extension
See `docs/EXTENSION.md`.

## 7. Verify
```bash
npm run diagnose     # PASS/FAIL per subsystem
```
Or call `system_health` from any connected client.
