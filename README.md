# OMNIBRIDGE AI — Universal MCP

**Universal AI tooling ecosystem · Autonomous agent engine · Web bridge · Roblox Studio integration**

OMNIBRIDGE turns any MCP-compatible AI (Claude Code, Claude Desktop, Cursor, VS Code,
ChatGPT/Codex, custom hosts) into an agent that can **research, inspect, build, test and
fix real projects** — including Roblox games in Studio — through **63 real MCP tools**,
a persistent knowledge engine, and an autonomous multi-agent executor.

> No fake tools. Every tool is implemented, tested, and honestly reports when its
> backend (Roblox Studio, browser extension) is not connected.

## Quick start
```bash
npm install
npm run build
npm start            # stdio + HTTP (dashboard on http://127.0.0.1:8765)
npm run diagnose     # PASS/FAIL per subsystem
```
Then connect a client — see [`docs/CONNECT.md`](docs/CONNECT.md).

## What you get
| Component | Description |
|---|---|
| **MCP Server** | Official SDK 1.32.2, stdio + Streamable HTTP, tools/resources/prompts, zod validation |
| **63 tools** | system, files, code, web, knowledge, Roblox (13), agent (10), browser (7), plugins |
| **Knowledge Engine** | SQLite FTS5 + TF-IDF hybrid retrieval, citations, persistent memory |
| **Agent Engine** | Planner + executor loop with checkpoints, retries, cancellation, 7 roles |
| **Roblox Studio** | Proxies the **official** Studio MCP server + Rojo disk layer + Luau analyzer |
| **Browser extension** | MV3 (Chromium/Firefox), 4 modes, long-poll bridge |
| **Desktop Bridge** | Native Messaging host, fixed command allowlist |
| **Dashboard** | Vanilla SPA: health, MCP explorer, Roblox, agents, knowledge, audit |
| **Security** | Permission levels L1–L4, token auth, sandbox, backups, audit, secret redaction |

## Example mission
> *"Crée-moi un jeu Roblox de combat arène avec 3 armes et un système de progression."*

The agent inspects the project → researches Roblox docs → plans → builds Luau systems →
analyzes/tests → fixes errors → presents a sourced report. A complete playable example
ships in [`examples/roblox-combat-game/`](examples/roblox-combat-game/README.md).

## Docs
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — system design
- [`docs/CONNECT.md`](docs/CONNECT.md) — connect Claude/Cursor/VS Code/ChatGPT + Studio
- [`docs/SECURITY.md`](docs/SECURITY.md) — permission model & boundaries
- [`docs/TOOLS.md`](docs/TOOLS.md) — full tool catalogue
- [`docs/ROBLOX.md`](docs/ROBLOX.md) — Studio integration details
- [`docs/EXTENSION.md`](docs/EXTENSION.md) — browser extension

## Tests
```bash
npm test   # node:test — registry, permissions, sandbox, knowledge, planner, executor, Luau, MCP protocol
```

## License
MIT — see `LICENSE`.
