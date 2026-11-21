# OMNIBRIDGE AI — Architecture

```
┌──────────────────────── AI clients (MCP) ────────────────────────┐
│ Claude Code · Claude Desktop · Cursor · VS Code · ChatGPT/Codex  │
│ + any MCP-compatible host (stdio or Streamable HTTP)             │
└──────────────────────────────┬───────────────────────────────────┘
                               │ JSON-RPC 2.0 (official MCP SDK)
┌──────────────────────────────▼───────────────────────────────────┐
│ OMNIBRIDGE CORE (src/)                                           │
│  Registry · Permissions (L1-L4) · Audit · Sandbox · SQLite       │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌──────────────┐  │
│  │ MCP Server │ │ Knowledge  │ │ Agent      │ │ Roblox       │  │
│  │ stdio+HTTP │ │ Engine     │ │ Engine     │ │ Connector    │  │
│  │ tools/     │ │ FTS5+TFIDF │ │ planner +  │ │ → official   │  │
│  │ resources/ │ │ memory     │ │ executor   │ │   Studio MCP │  │
│  │ prompts/   │ │            │ │ 7 roles    │ │ → Rojo files │  │
│  └────────────┘ └────────────┘ └────────────┘ └──────────────┘  │
└──┬──────────────┬──────────────┬──────────────┬──────────────────┘
   │              │              │              │
   ▼              ▼              ▼              ▼
┌───────┐  ┌────────────┐ ┌──────────┐  ┌────────────────────┐
│Dashboard│  │ Browser    │ │ Desktop  │  │ Roblox Studio      │
│ (HTTP) │  │ Extension  │ │ Bridge   │  │ (official MCP)     │
│ /api/* │  │ MV3 + poll │ │ native   │  │ + Rojo projects    │
└────────┘  └────────────┘ └──────────┘  └────────────────────┘
```

## Modules
- **Core** (`src/core/`): tool registry, permission checks, audit log, path sandbox, SQLite storage (`node:sqlite`, zero native deps).
- **MCP layer** (`src/mcp/server.ts`): official `@modelcontextprotocol/sdk` 1.32.2 — `McpServer`, `StdioServerTransport`, `StreamableHTTPServerTransport` (stateful sessions). JSON Schema → zod conversion for input validation. Tool annotations (`readOnlyHint`, `destructiveHint`, …).
- **Knowledge Engine** (`src/knowledge/`): chunking (1200 chars, 200 overlap), FTS5 + TF-IDF hybrid retrieval, citations with source/version/date/reliability, curated official doc sources, persistent memory (personal/project/temp scopes).
- **Agent Engine** (`src/agent/`): deterministic planner (keyword routing over the real tool catalogue), executor loop ANALYSE→…→VALIDATION with checkpoints (SQLite), retries, step limits, cancellation, repeated-error detection, 7 specialized roles.
- **Roblox** (`src/roblox/`): official Studio MCP discovery + MCP-client proxy; Rojo disk layer; Luau static analyzer (services/classes/deprecated APIs/delimiters); embedded Luau knowledge base.
- **Browser bridge** (`src/browser/bridge.ts`): in-process hub, extension long-polls for commands, results return over HTTP. Honest failure when disconnected.
- **HTTP app** (`src/http/app.ts`): `/mcp` (Streamable HTTP, token + Origin checks), `/api/*` (dashboard), `/bridge/*` (extension), static dashboard.
- **Dashboard** (`dashboard/`): vanilla JS SPA, no build step.
- **Extension** (`extension/`): MV3, Chromium + Firefox-compatible, 4 modes.
- **Desktop Bridge** (`desktop-bridge/`): Native Messaging host (length-prefixed JSON), install scripts.
- **Plugins** (`plugins/`): manifest-based connectors, validated by `plugin_diagnose`.

## Data flow (tool call)
1. MCP client → `tools/call` → SDK validates args (zod).
2. `callTool()` → permission check (level vs config, `confirm` for L4) → handler.
3. Handler may call other tools (composite), the Studio MCP proxy, the browser bridge, or the knowledge engine.
4. Result → audit log → MCP response (text content, secrets redacted).

## Storage
`~/.omnibridge/omnibridge.db` (SQLite): memory, knowledge chunks + FTS5, tasks, checkpoints, audit.
`~/.omnibridge/token.txt` (0600): local API token. `~/.omnibridge/backups/`: file backups.
