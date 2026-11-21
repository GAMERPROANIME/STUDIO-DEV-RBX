# Roblox Studio integration

## Principle
OMNIBRIDGE does **not** reimplement Studio. It uses Roblox's **official Studio MCP server**
(built into Studio since 2025) as the primary connector, and adds a Rojo/disk layer
that works without Studio running.

## Live Studio (official MCP)
1. Open a place in Roblox Studio, sign in.
2. Assistant → Settings → MCP Servers → enable **Enable Studio as MCP server**.
3. Set `ROBLOX_STUDIO_MCP_COMMAND` (Windows: `%LOCALAPPDATA%\Roblox\mcp.bat`;
   macOS: `StudioMCP` inside `RobloxStudio.app`).
4. Restart OMNIBRIDGE. `roblox_list_studios` now proxies Roblox's own tools
   (`list_roblox_studios`, `get_studio_state`, `script_read`, `inspect_instance`,
   `screen_capture`, playtest, console…). OMNIBRIDGE discovers the tool names
   at runtime and delegates — no duplication, no guessing.

## Rojo projects (no Studio needed)
`roblox_inspect_project`, `roblox_search_scripts`, `roblox_read_script`,
`roblox_edit_scripts` operate on `.luau`/`.lua` files on disk with backups
and static analysis after every edit. See `examples/roblox-combat-game/`.

## Luau intelligence
- `code_analyze` validates services (`game:GetService`), classes (`Instance.new`),
  deprecated APIs (`wait()` → `task.wait()`), balanced delimiters, `--!strict`.
- `knowledge_index_luau` indexes the embedded Luau/Roblox knowledge base.
- `roblox-plugin/OmniBridgePlugin.server.luau` is a complementary Studio plugin
  (selection + HTTP to the local bridge) for plugin-only capabilities.

## Debugging loop
`roblox_get_console_output` → `roblox_read_script` → `error_diagnose` →
fix (`roblox_edit_scripts` / `roblox_execute_luau`) → `roblox_playtest` →
verify the error is gone (including indirect errors).

## Honest limits
- Without Studio MCP configured, live tools (`roblox_execute_luau`,
  `roblox_create_objects`, `roblox_playtest`, `roblox_capture_screen`, …)
  return `available: false` + setup instructions. They never fake results.
- `.rbxl` binary places cannot be parsed by OMNIBRIDGE — use Rojo source or live Studio.
