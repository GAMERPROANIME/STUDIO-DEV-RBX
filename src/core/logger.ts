/** Structured logger. Logs go to stderr so stdout stays clean for stdio MCP. */
export type LogLevel = "debug" | "info" | "warn" | "error";

const levelRank: Record<LogLevel, number> = { debug: 0, info: 1, warn: 2, error: 3 };
const minLevel = (process.env.OMNIBRIDGE_LOG_LEVEL as LogLevel) ?? "info";

function emit(level: LogLevel, msg: string, meta?: Record<string, unknown>): void {
  if (levelRank[level] < levelRank[minLevel]) return;
  const line = JSON.stringify({ ts: new Date().toISOString(), level, msg, ...(meta ?? {}) });
  process.stderr.write(line + "\n");
}

export const log = {
  debug: (m: string, meta?: Record<string, unknown>) => emit("debug", m, meta),
  info: (m: string, meta?: Record<string, unknown>) => emit("info", m, meta),
  warn: (m: string, meta?: Record<string, unknown>) => emit("warn", m, meta),
  error: (m: string, meta?: Record<string, unknown>) => emit("error", m, meta),
};
