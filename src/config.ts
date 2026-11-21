import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join, resolve } from "node:path";

/** Permission levels (see docs/SECURITY.md) */
export type PermissionLevel = 1 | 2 | 3 | 4;

export interface OmniBridgeConfig {
  transport: "stdio" | "http" | "both";
  httpHost: string;
  httpPort: number;
  /** Local API token. Generated + persisted on first run if not provided. */
  token: string;
  /** Max permission level the agent may use without explicit confirmation. */
  permissionLevel: PermissionLevel;
  /** Workspace root the file tools are sandboxed to. */
  workspaceRoot: string;
  /** Directory for SQLite DB, backups, checkpoints. */
  dataDir: string;
  /** Max file size (bytes) readable via tools. */
  maxFileBytes: number;
  /** Agent executor limits. */
  agentMaxSteps: number;
  agentMaxRetries: number;
  agentStepTimeoutMs: number;
  /** Official Roblox Studio MCP command (optional). */
  robloxStudioMcpCommand?: string;
  robloxStudioMcpArgs: string[];
  /** Allowed external hosts for web tools (empty = allow all http/https). */
  webAllowedHosts: string[];
  /** Dashboard static dir. */
  dashboardDir: string;
  /** Plugins dir. */
  pluginsDir: string;
  /** Require token on the local HTTP API (default true). */
  requireToken: boolean;
}

function envInt(name: string, fallback: number): number {
  const v = process.env[name];
  if (!v) return fallback;
  const n = Number.parseInt(v, 10);
  return Number.isFinite(n) ? n : fallback;
}

function loadDotEnv(dir: string): void {
  const p = join(dir, ".env");
  if (!existsSync(p)) return;
  for (const line of readFileSync(p, "utf8").split(/\r?\n/)) {
    const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$/i);
    if (m && !(m[1] in process.env)) process.env[m[1]] = m[2].replace(/^["']|["']$/g, "");
  }
}

export function defaultDataDir(): string {
  const base = process.env.OMNIBRIDGE_DATA_DIR;
  if (base) return resolve(base);
  return join(homedir(), ".omnibridge");
}

export function loadConfig(overrides: Partial<OmniBridgeConfig> = {}): OmniBridgeConfig {
  const root = resolve(process.cwd());
  loadDotEnv(root);
  const dataDir = defaultDataDir();
  const tokenFile = join(dataDir, "token.txt");
  let token = process.env.OMNIBRIDGE_TOKEN ?? "";
  if (!token && existsSync(tokenFile)) token = readFileSync(tokenFile, "utf8").trim();
  if (!token) {
    // Generated lazily by ensureToken() in db init; keep empty here.
    token = "";
  }
  const level = envInt("OMNIBRIDGE_PERMISSION_LEVEL", 2);
  const cfg: OmniBridgeConfig = {
    transport: (process.env.OMNIBRIDGE_TRANSPORT as OmniBridgeConfig["transport"]) ?? "both",
    httpHost: process.env.OMNIBRIDGE_HTTP_HOST ?? "127.0.0.1",
    httpPort: envInt("OMNIBRIDGE_HTTP_PORT", 8765),
    token,
    permissionLevel: (level >= 1 && level <= 4 ? level : 2) as PermissionLevel,
    workspaceRoot: resolve(process.env.OMNIBRIDGE_WORKSPACE ?? root),
    dataDir,
    maxFileBytes: envInt("OMNIBRIDGE_MAX_FILE_BYTES", 2_000_000),
    agentMaxSteps: envInt("OMNIBRIDGE_AGENT_MAX_STEPS", 40),
    agentMaxRetries: envInt("OMNIBRIDGE_AGENT_MAX_RETRIES", 2),
    agentStepTimeoutMs: envInt("OMNIBRIDGE_AGENT_STEP_TIMEOUT_MS", 120_000),
    robloxStudioMcpCommand: process.env.ROBLOX_STUDIO_MCP_COMMAND || undefined,
    robloxStudioMcpArgs: process.env.ROBLOX_STUDIO_MCP_ARGS
      ? process.env.ROBLOX_STUDIO_MCP_ARGS.split(/\s+/).filter(Boolean)
      : [],
    webAllowedHosts: process.env.OMNIBRIDGE_WEB_ALLOWED_HOSTS
      ? process.env.OMNIBRIDGE_WEB_ALLOWED_HOSTS.split(",").map((s) => s.trim()).filter(Boolean)
      : [],
    dashboardDir: resolve(process.env.OMNIBRIDGE_DASHBOARD_DIR ?? join(root, "dashboard")),
    pluginsDir: resolve(process.env.OMNIBRIDGE_PLUGINS_DIR ?? join(root, "plugins")),
    requireToken: process.env.OMNIBRIDGE_REQUIRE_TOKEN !== "0",
  };
  return { ...cfg, ...overrides };
}

export function ensureToken(cfg: OmniBridgeConfig): string {
  if (cfg.token) return cfg.token;
  const { mkdirSync, writeFileSync } = requireFs();
  mkdirSync(cfg.dataDir, { recursive: true });
  const { randomBytes } = requireCrypto();
  const token = randomBytes(32).toString("hex");
  writeFileSync(join(cfg.dataDir, "token.txt"), token + "\n", { mode: 0o600 });
  cfg.token = token;
  return token;
}

// Small indirection to keep ESM happy without top-level await tricks.
import { mkdirSync as _mkdir, writeFileSync as _write } from "node:fs";
import { randomBytes as _rb } from "node:crypto";
function requireFs() { return { mkdirSync: _mkdir, writeFileSync: _write }; }
function requireCrypto() { return { randomBytes: _rb }; }
