#!/usr/bin/env node
/**
 * OMNIBRIDGE AI — Universal MCP entry point.
 * Transports: stdio (default for MCP clients) and/or Streamable HTTP.
 * Usage:
 *   node dist/index.js                  # stdio + HTTP (both)
 *   OMNIBRIDGE_TRANSPORT=stdio node dist/index.js
 *   OMNIBRIDGE_TRANSPORT=http node dist/index.js
 *   node dist/index.js --diagnose       # run diagnostics and exit
 */
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { loadConfig, ensureToken } from "./config.js";
import { Db } from "./core/db.js";
import { Registry } from "./core/registry.js";
import { checkPermission } from "./core/permissions.js";
import { log } from "./core/logger.js";
import { KnowledgeEngine } from "./knowledge/engine.js";
import { TaskExecutor } from "./agent/executor.js";
import { RobloxConnector } from "./roblox/connector.js";
import { BrowserBridge } from "./browser/bridge.js";
import { registerSystemTools } from "./tools/system.js";
import { registerFileTools } from "./tools/files.js";
import { registerCodeTools } from "./tools/code.js";
import { registerWebTools } from "./tools/web.js";
import { registerKnowledgeTools } from "./tools/knowledge.js";
import { registerRobloxTools } from "./tools/roblox.js";
import { registerAgentTools } from "./tools/agent.js";
import { registerBrowserTools } from "./tools/browser.js";
import { registerPluginTools } from "./tools/plugins.js";
import { buildMcpServer } from "./mcp/server.js";
import { startHttpServer } from "./http/app.js";

async function main(): Promise<void> {
  const cfg = loadConfig();
  const db = new Db(cfg);
  const reg = new Registry();
  const knowledge = new KnowledgeEngine(db);
  const roblox = new RobloxConnector(cfg);
  const bridge = new BrowserBridge();

  // Central tool caller: permission check + audit + dispatch.
  const callTool = async (name: string, args: Record<string, unknown>, confirmed = false): Promise<unknown> => {
    const tool = reg.get(name);
    if (!tool) throw new Error(`Unknown tool: ${name}`);
    checkPermission(cfg, tool, { ...args, confirm: confirmed });
    try {
      const result = await tool.handler(args, { config: cfg, db, callTool: (n, a) => callTool(n, a, confirmed), confirmed });
      db.audit(name, tool.level, true);
      return result;
    } catch (e) {
      db.audit(name, tool.level, false, e instanceof Error ? e.message : String(e));
      throw e;
    }
  };

  const executor = new TaskExecutor(cfg, db, (n, a) => callTool(n, a));

  registerSystemTools(reg, {
    robloxInfo: () => roblox.info(),
    bridgeStatus: () => bridge.status(),
    knowledgeStats: () => knowledge.stats(),
  });
  registerFileTools(reg);
  registerCodeTools(reg);
  registerWebTools(reg);
  registerKnowledgeTools(reg, knowledge);
  registerRobloxTools(reg, roblox);
  registerAgentTools(reg, executor);
  registerBrowserTools(reg, bridge);
  registerPluginTools(reg);

  // First run: seed the Luau/Roblox knowledge base so retrieval works immediately.
  if (knowledge.stats().chunks === 0) {
    const { LUAU_KNOWLEDGE } = await import("./roblox/luau.js");
    const r = knowledge.indexDocument({ source: "luau-knowledge", title: "Luau & Roblox Knowledge Base", text: LUAU_KNOWLEDGE, reliability: "official" });
    log.info("seeded knowledge base", { chunks: r.chunks });
  }

  log.info("omnibridge ready", { tools: reg.size, categories: reg.categories(), permissionLevel: cfg.permissionLevel });

  if (process.argv.includes("--diagnose")) {
    ensureToken(cfg);
    const health = (await callTool("system_diagnostics", {})) as { ok: boolean; checks: Array<Record<string, unknown>> };
    for (const c of health.checks) process.stdout.write(`${c.ok ? "PASS" : "FAIL"}  ${String(c.name)} — ${String(c.detail)}\n`);
    process.stdout.write(health.ok ? "ALL CHECKS PASSED\n" : "SOME CHECKS FAILED (see above)\n");
    db.close();
    process.exit(health.ok ? 0 : 1);
  }

  const wantStdio = cfg.transport === "stdio" || cfg.transport === "both";
  const wantHttp = cfg.transport === "http" || cfg.transport === "both";

  if (wantHttp) {
    ensureToken(cfg);
    startHttpServer({ cfg, reg, db, bridge, executor, knowledge, roblox, callTool });
  }
  if (wantStdio) {
    const mcp = buildMcpServer(cfg, reg, db, callTool);
    const transport = new StdioServerTransport();
    await mcp.connect(transport);
    log.info("stdio transport connected");
  }
  if (!wantStdio && !wantHttp) {
    log.error("no transport configured");
    process.exit(1);
  }

  const shutdown = async () => {
    log.info("shutting down");
    await roblox.close();
    db.close();
    process.exit(0);
  };
  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);
}

main().catch((e) => {
  process.stderr.write(`Fatal: ${e instanceof Error ? e.stack ?? e.message : String(e)}\n`);
  process.exit(1);
});
