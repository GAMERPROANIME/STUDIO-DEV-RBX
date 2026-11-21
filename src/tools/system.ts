import { platform, arch, tmpdir, freemem, totalmem, cpus, loadavg } from "node:os";
import { existsSync, statSync } from "node:fs";
import { join } from "node:path";
import type { Registry } from "../core/registry.js";
import type { ToolDef } from "../core/permissions.js";
import { DOC_SOURCES } from "../knowledge/sources.js";

const str = { type: "string" } as const;

export function registerSystemTools(reg: Registry, deps: { robloxInfo: () => Promise<unknown>; bridgeStatus: () => unknown; knowledgeStats: () => unknown }): void {
  const tools: ToolDef[] = [
    {
      name: "system_health",
      description: "Health check for OMNIBRIDGE: runtime, workspace, data dir, tool count, connected subsystems (Roblox Studio MCP, browser extension, knowledge base). Call this first to know what is available.",
      inputSchema: { type: "object", properties: {} },
      level: 1, category: "system", readOnly: true,
      handler: async (_args, ctx) => {
        const [roblox, bridge] = await Promise.all([deps.robloxInfo(), Promise.resolve(deps.bridgeStatus())]);
        return {
          ok: true,
          version: "1.0.0",
          runtime: { node: process.version, platform: platform(), arch: arch(), pid: process.pid },
          workspace: ctx.config.workspaceRoot,
          workspaceExists: existsSync(ctx.config.workspaceRoot),
          dataDir: ctx.config.dataDir,
          permissionLevel: ctx.config.permissionLevel,
          transport: ctx.config.transport,
          toolCount: reg.size,
          categories: reg.categories(),
          memory: { freeBytes: freemem(), totalBytes: totalmem(), cpus: cpus().length, loadAvg: loadavg() },
          robloxStudio: roblox,
          browserBridge: bridge,
          knowledge: deps.knowledgeStats(),
          tmpDir: tmpdir(),
        };
      },
    },
    {
      name: "system_list_tools",
      description: "List every registered MCP tool with its category, permission level and description. Use to discover capabilities before acting.",
      inputSchema: { type: "object", properties: { category: { ...str, description: "Optional category filter" } } },
      level: 1, category: "system", readOnly: true,
      handler: (args) => {
        const cat = args.category as string | undefined;
        return reg.list()
          .filter((t) => !cat || t.category === cat)
          .map((t) => ({ name: t.name, category: t.category, level: t.level, readOnly: t.readOnly, description: t.description }));
      },
    },
    {
      name: "system_diagnostics",
      description: "Deep diagnostics: checks workspace writability, DB, knowledge index, doc sources reachability config, Studio MCP discovery, bridge status. Returns pass/fail per check with remediation hints.",
      inputSchema: { type: "object", properties: {} },
      level: 1, category: "system", readOnly: true,
      handler: async (_args, ctx) => {
        const checks: Array<Record<string, unknown>> = [];
        const push = (name: string, ok: boolean, detail: string) => checks.push({ name, ok, detail });
        push("workspace", existsSync(ctx.config.workspaceRoot), ctx.config.workspaceRoot);
        try { push("dataDir", existsSync(ctx.config.dataDir) && statSync(ctx.config.dataDir).isDirectory(), ctx.config.dataDir); }
        catch { push("dataDir", false, ctx.config.dataDir); }
        push("token", Boolean(ctx.config.token), ctx.config.token ? "configured" : "will be generated on HTTP start");
        push("node", Number(process.versions.node.split(".")[0]) >= 22, `node ${process.versions.node} (requires >=22 for node:sqlite)`);
        push("dashboard", existsSync(join(ctx.config.dashboardDir, "index.html")), ctx.config.dashboardDir);
        push("pluginsDir", existsSync(ctx.config.pluginsDir), ctx.config.pluginsDir);
        const roblox = (await deps.robloxInfo()) as { available?: boolean; error?: string };
        // Optional subsystems: absence is not a failure, but it is reported honestly.
        push("robloxStudioMcp", true, roblox.available ? "connected" : `not configured (optional) — ${roblox.error ?? ""}`);
        const bridge = deps.bridgeStatus() as { connected?: boolean };
        push("browserExtension", true, bridge.connected ? "connected" : "not connected (optional)");
        const ks = deps.knowledgeStats() as { chunks?: number };
        push("knowledgeBase", (ks.chunks ?? 0) > 0, `${ks.chunks ?? 0} chunks indexed`);
        push("docSources", DOC_SOURCES.length > 0, `${DOC_SOURCES.length} curated sources`);
        return { ok: checks.every((c) => c.ok), checks };
      },
    },
    {
      name: "system_audit_log",
      description: "Recent audit log of tool calls (tool, permission level, success/failure). Use for security review and debugging.",
      inputSchema: { type: "object", properties: { limit: { type: "integer", minimum: 1, maximum: 500, default: 50 } } },
      level: 1, category: "system", readOnly: true,
      handler: (args, ctx) => ctx.db.auditRecent(Number(args.limit ?? 50)),
    },
  ];
  for (const t of tools) reg.register(t);
}
