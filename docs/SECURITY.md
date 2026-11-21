# Security model

## Permission levels
| Level | Name | Meaning |
|---|---|---|
| 1 | Read | Inspect/search/retrieve. No mutation. |
| 2 | Assistance | Writes allowed with backup + audit (default). |
| 3 | Controlled automation | Reversible local ops (create/update files, index docs, execute Luau in Studio). |
| 4 | Sensitive | Destructive/external/irreversible — requires `confirm=true` per call. |

Configure with `OMNIBRIDGE_PERMISSION_LEVEL` (1–4, default 2). A tool above the
configured level is rejected with a clear error.

## Boundaries
- **HTTP binds to 127.0.0.1 by default.** Never expose it without TLS + strong auth.
- **Token auth** on `/mcp` and `/api/*` (Bearer, from `~/.omnibridge/token.txt`, mode 0600).
- **Origin check** on `/mcp` (DNS-rebinding protection): only localhost origins.
- **Path sandbox**: file tools cannot escape `OMNIBRIDGE_WORKSPACE` (symlinks checked).
- **Backups before writes**: every `file_update` copies the previous version to `~/.omnibridge/backups/`.
- **Audit log**: every tool call (tool, level, ok/error) in SQLite + `system_audit_log`.
- **Secret redaction**: memory, audit and tool results redact `api_key/token/secret/password` patterns and known token formats.
- **Prompt-injection guard**: web/browser content is wrapped as UNTRUSTED DATA. It can never trigger tool calls, permission changes or policy edits.
- **Desktop Bridge**: fixed command allowlist; never executes arbitrary shell commands.
- **Extension**: never reads cookies, passwords or form fields; only user-authorized page text/selection/links.

## What OMNIBRIDGE will NOT do
- Bypass provider restrictions, scrape credentials, or fake compatibility.
- Claim a tool works when its backend (Studio, extension) is disconnected — it returns an honest error with setup instructions.
