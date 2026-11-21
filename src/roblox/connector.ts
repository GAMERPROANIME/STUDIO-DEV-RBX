import { existsSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import type { OmniBridgeConfig } from "../config.js";
import { log } from "../core/logger.js";

/**
 * Roblox Studio connector.
 * Primary path: the OFFICIAL Studio MCP server built into Roblox Studio
 * (Assistant → Settings → MCP Servers → "Enable Studio as MCP server").
 * OMNIBRIDGE discovers its command, connects as an MCP client, lists its
 * tools and proxies calls — it never duplicates Studio's own capabilities.
 * Secondary path: Rojo project files on disk (works without Studio running).
 */
export interface StudioMcpInfo {
  available: boolean;
  command?: string;
  args: string[];
  tools: string[];
  error?: string;
  setupInstructions: string;
}

export const STUDIO_SETUP_INSTRUCTIONS = [
  "1. Install Roblox Studio and sign in, then open a place.",
  "2. In Studio: Assistant → Settings → MCP Servers → enable 'Enable Studio as MCP server'.",
  "3. Point OMNIBRIDGE at the server: set ROBLOX_STUDIO_MCP_COMMAND to the StudioMCP binary",
  "   (Windows: %LOCALAPPDATA%\\Roblox\\mcp.bat · macOS: StudioMCP inside RobloxStudio.app).",
  "4. Restart OMNIBRIDGE. roblox_list_studios should then report the open place.",
  "Alternative (no Studio needed): use a Rojo project — OMNIBRIDGE reads/edits .luau files directly.",
].join("\n");

export function discoverStudioMcpCommand(cfg: OmniBridgeConfig): { command?: string; args: string[] } {
  if (cfg.robloxStudioMcpCommand) return { command: cfg.robloxStudioMcpCommand, args: cfg.robloxStudioMcpArgs };
  const candidates: string[] = [];
  if (process.platform === "win32") {
    const local = process.env.LOCALAPPDATA ?? join(homedir(), "AppData", "Local");
    candidates.push(join(local, "Roblox", "mcp.bat"));
  } else if (process.platform === "darwin") {
    candidates.push("/Applications/RobloxStudio.app/Contents/MacOS/StudioMCP");
    candidates.push(join(homedir(), "Applications/RobloxStudio.app/Contents/MacOS/StudioMCP"));
  }
  for (const c of candidates) if (existsSync(c)) return { command: c, args: [] };
  return { args: [] };
}

export class RobloxConnector {
  private client: Client | null = null;
  private tools: string[] = [];
  private lastError: string | null = null;
  private connecting: Promise<void> | null = null;

  constructor(private cfg: OmniBridgeConfig) {}

  async info(): Promise<StudioMcpInfo> {
    const { command, args } = discoverStudioMcpCommand(this.cfg);
    if (!command) {
      return { available: false, args, tools: [], error: "Studio MCP command not found", setupInstructions: STUDIO_SETUP_INSTRUCTIONS };
    }
    try {
      await this.ensureConnected(command, args);
      return { available: true, command, args, tools: this.tools, setupInstructions: STUDIO_SETUP_INSTRUCTIONS };
    } catch (e) {
      return { available: false, command, args, tools: [], error: e instanceof Error ? e.message : String(e), setupInstructions: STUDIO_SETUP_INSTRUCTIONS };
    }
  }

  private ensureConnected(command: string, args: string[]): Promise<void> {
    if (this.client) return Promise.resolve();
    if (this.connecting) return this.connecting;
    this.connecting = (async () => {
      const client = new Client({ name: "omnibridge-roblox-client", version: "1.0.0" }, { capabilities: {} });
      const transport = new StdioClientTransport({ command, args, stderr: "pipe" });
      await client.connect(transport);
      const listed = await client.listTools();
      this.tools = listed.tools.map((t) => t.name);
      this.client = client;
      log.info("connected to official Studio MCP", { command, tools: this.tools });
    })().catch((e) => {
      this.lastError = e instanceof Error ? e.message : String(e);
      this.connecting = null;
      throw e;
    });
    return this.connecting;
  }

  /** Proxy a call to the official Studio MCP server. Throws if unavailable. */
  async callTool(name: string, args: Record<string, unknown>): Promise<unknown> {
    const { command, args: cmdArgs } = discoverStudioMcpCommand(this.cfg);
    if (!command) throw new Error(`Official Studio MCP server not configured. ${STUDIO_SETUP_INSTRUCTIONS}`);
    await this.ensureConnected(command, cmdArgs);
    if (!this.client) throw new Error(this.lastError ?? "Studio MCP unavailable");
    const result = await this.client.callTool({ name, arguments: args });
    return result;
  }

  async listTools(): Promise<string[]> {
    const info = await this.info();
    return info.tools;
  }

  async close(): Promise<void> {
    try { await this.client?.close(); } catch { /* ignore */ }
    this.client = null;
  }
}
