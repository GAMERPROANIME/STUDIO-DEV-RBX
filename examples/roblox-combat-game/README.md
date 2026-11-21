# Example: Arena Combat Game (Rojo project)

A complete, playable Roblox arena combat game built as a Rojo project —
the reference mission for OMNIBRIDGE (`roblox-game-mission` prompt).

## Systems
- **CombatServer** (`src/server/CombatServer.server.luau`) — authoritative damage,
  range/cooldown validation, knockback. Never trusts the client.
- **CombatClient** (`src/client/CombatClient.client.luau`) — input, target hinting.
- **ArenaManager** (`src/server/ArenaManager.server.luau`) — spawns, XP/levels.
- **CombatConfig** (`src/shared/CombatConfig.luau`) — shared weapon tuning.

## Build & run
```bash
rojo build -o game.rbxl
# then open game.rbxl in Roblox Studio and press Play
```

## Work on it with OMNIBRIDGE
1. Start OMNIBRIDGE: `npm start` (from the repo root).
2. Connect an MCP client (see `docs/CONNECT.md`) or use the dashboard.
3. Enable Studio's MCP server (Assistant → Settings → MCP Servers) for live editing.
4. Ask the AI: *"Crée/améliore un jeu de combat arène avec 3 armes et un système de progression"* —
   it will inspect this project, plan, edit, analyze and test.

## Extend it
- Add weapons in `CombatConfig.Weapons` (server validates automatically).
- Add a `RemoteEvent` in `project.json` under `Remotes` for new client→server actions.
- Add VFX: `ParticleEmitter` under `ReplicatedStorage.Shared` assets.
