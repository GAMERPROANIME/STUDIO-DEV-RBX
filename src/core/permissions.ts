import type { OmniBridgeConfig, PermissionLevel } from "../config.js";

/**
 * Permission model (docs/SECURITY.md):
 *  L1 Read        — inspect, search, retrieve. No mutation.
 *  L2 Assistance  — prepare changes; writes require backup + are logged.
 *  L3 Controlled automation — reversible local ops allowed automatically.
 *  L4 Sensitive   — destructive / external / irreversible: needs explicit confirm.
 */
export interface ToolDef {
  name: string;
  description: string;
  /** JSON Schema for input (also used to build the zod shape in the MCP layer). */
  inputSchema: Record<string, unknown>;
  level: PermissionLevel;
  category: string;
  /** Read-only tools can run at any configured level. */
  readOnly: boolean;
  /** Handler receives validated args + context. */
  handler: (args: Record<string, unknown>, ctx: ToolContext) => Promise<unknown> | unknown;
}

export interface ToolContext {
  config: OmniBridgeConfig;
  db: import("./db.js").Db;
  /** Call another registered tool (agent executor, composite tools). */
  callTool: (name: string, args: Record<string, unknown>) => Promise<unknown>;
  /** True when the caller explicitly confirmed a sensitive operation. */
  confirmed: boolean;
  signal?: AbortSignal;
}

export class PermissionError extends Error {
  constructor(message: string) { super(message); this.name = "PermissionError"; }
}

/** Redact likely secrets before they reach memory/audit/logs. */
export function redactSecrets(text: string): string {
  return text
    .replace(/(api[_-]?key|token|secret|password|passwd|pwd)\s*[:=]\s*\S+/gi, "$1=[REDACTED]")
    .replace(/\b(gh[pousr]_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16})\b/g, "[REDACTED]");
}

export function checkPermission(cfg: OmniBridgeConfig, tool: ToolDef, args: Record<string, unknown>): void {
  if (tool.level <= cfg.permissionLevel) {
    if (tool.level === 4 && args.confirm !== true) {
      throw new PermissionError(
        `Tool "${tool.name}" is level 4 (sensitive). Pass confirm=true to proceed. ` +
        `This operation is destructive, external or irreversible.`
      );
    }
    return;
  }
  throw new PermissionError(
    `Tool "${tool.name}" requires permission level ${tool.level}, ` +
    `but the server is configured for level ${cfg.permissionLevel}. ` +
    `Raise OMNIBRIDGE_PERMISSION_LEVEL or use a lower-level tool.`
  );
}
