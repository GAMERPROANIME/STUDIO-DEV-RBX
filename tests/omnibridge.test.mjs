/**
 * OMNIBRIDGE test suite (node:test). Run: npm test
 * Covers: registry, permissions, sandbox, knowledge retrieval, planner,
 * executor (mock tools), Luau analyzer, MCP protocol (in-memory client),
 * file tools, plugin diagnostics.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { loadConfig } from "../dist/config.js";
import { Db } from "../dist/core/db.js";
import { Registry } from "../dist/core/registry.js";
import { checkPermission, PermissionError, redactSecrets } from "../dist/core/permissions.js";
import { sandboxResolve } from "../dist/core/sandbox.js";
import { KnowledgeEngine, chunkText } from "../dist/knowledge/engine.js";
import { createPlan } from "../dist/agent/planner.js";
import { TaskExecutor } from "../dist/agent/executor.js";
import { analyzeLuau } from "../dist/roblox/luau.js";
import { registerFileTools } from "../dist/tools/files.js";
import { registerCodeTools } from "../dist/tools/code.js";
import { registerKnowledgeTools } from "../dist/tools/knowledge.js";
import { registerAgentTools } from "../dist/tools/agent.js";
import { registerPluginTools, listConnectors } from "../dist/tools/plugins.js";
import { buildMcpServer } from "../dist/mcp/server.js";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";

function makeCtx() {
  const root = mkdtempSync(join(tmpdir(), "omnibridge-test-"));
  const dataDir = join(root, "data");
  const workspace = join(root, "ws");
  mkdirSync(workspace, { recursive: true });
  const cfg = loadConfig({ workspaceRoot: workspace, dataDir, permissionLevel: 3, token: "test-token" });
  const db = new Db(cfg);
  const reg = new Registry();
  const knowledge = new KnowledgeEngine(db);
  const callTool = async (name, args, confirmed = false) => {
    const tool = reg.get(name);
    if (!tool) throw new Error(`Unknown tool: ${name}`);
    checkPermission(cfg, tool, { ...args, confirm: confirmed });
    return tool.handler(args, { config: cfg, db, callTool: (n, a) => callTool(n, a, confirmed), confirmed });
  };
  const executor = new TaskExecutor(cfg, db, (n, a) => callTool(n, a));
  registerFileTools(reg);
  registerCodeTools(reg);
  registerKnowledgeTools(reg, knowledge);
  registerAgentTools(reg, executor);
  registerPluginTools(reg);
  return { root, cfg, db, reg, knowledge, executor, callTool };
}

test("registry: register, list, duplicate rejection", () => {
  const { reg } = makeCtx();
  assert.ok(reg.size >= 10);
  assert.throws(() => reg.register(reg.list()[0]), /Duplicate/);
  const cats = reg.categories();
  assert.ok(cats.files.includes("file_read"));
});

test("permissions: level gate + confirm gate + redaction", () => {
  const { cfg } = makeCtx();
  const tool = { name: "x", level: 4, readOnly: false };
  // Configured level is 3: L4 is rejected even with confirm.
  assert.throws(() => checkPermission(cfg, tool, { confirm: true }), PermissionError);
  // With level 4 configured, confirm=true is still required.
  cfg.permissionLevel = 4;
  assert.throws(() => checkPermission(cfg, tool, {}), PermissionError);
  checkPermission(cfg, tool, { confirm: true });
  assert.equal(redactSecrets("api_key=abc123"), "api_key=[REDACTED]");
  assert.match(redactSecrets("ghp_123456789012345678901234567890123456"), /REDACTED/);
});

test("sandbox: escapes rejected, inside allowed", () => {
  const { cfg } = makeCtx();
  assert.throws(() => sandboxResolve(cfg.workspaceRoot, "../etc/passwd"), /escapes/);
  assert.throws(() => sandboxResolve(cfg.workspaceRoot, "/etc/passwd"), /escapes/);
  assert.ok(sandboxResolve(cfg.workspaceRoot, "a/b.txt").endsWith("a/b.txt"));
});

test("knowledge: chunking + FTS/TF-IDF retrieval with citations", async () => {
  const { knowledge, callTool } = makeCtx();
  assert.ok(chunkText("x".repeat(3000)).length >= 2);
  await callTool("knowledge_index", { source: "test-doc", title: "Combat Guide", text: "RemoteEvent combat validation on the server. Never trust client damage values. Use task.wait for cooldowns." });
  const res = await callTool("knowledge_retrieve", { query: "RemoteEvent combat validation server", limit: 3 });
  assert.ok(res.count >= 1);
  assert.match(res.hits[0].citation, /test-doc/);
  assert.ok(res.hits[0].score > 0);
  const stats = knowledge.stats();
  assert.ok(stats.chunks >= 1 && stats.sources >= 1);
});

test("planner: roblox goal produces ordered plan with real tools", () => {
  const { reg } = makeCtx();
  const plan = createPlan("Crée un jeu Roblox de combat arène", { workspace: "." });
  assert.ok(plan.steps.length >= 4);
  for (const s of plan.steps) assert.ok(reg.get(s.tool), `tool ${s.tool} must exist`);
  // dependencies reference earlier steps
  const ids = new Set(plan.steps.map((s) => s.id));
  for (const s of plan.steps) for (const d of s.dependsOn) assert.ok(ids.has(d));
});

test("executor: runs plan, checkpoints, completes", async () => {
  const { executor, callTool } = makeCtx();
  const plan = {
    goal: "test",
    rationale: "test",
    steps: [
      { id: "s1", title: "list", tool: "file_list", args: { path: "." }, role: "coordinator", dependsOn: [], acceptance: "ok" },
      { id: "s2", title: "index", tool: "knowledge_index", args: { source: "t", title: "T", text: "hello world executor test" }, role: "coordinator", dependsOn: ["s1"], acceptance: "ok" },
    ],
  };
  const rec = executor.createTask("test goal", plan);
  const done = await executor.run(rec.id);
  assert.equal(done.status, "completed");
  assert.ok(done.results.s1.ok && done.results.s2.ok);
  const status = await callTool("agent_get_task_status", { taskId: rec.id });
  assert.equal(status.completed, 2);
  const cp = executor.restoreCheckpoint(rec.id);
  assert.equal(cp.restored, true);
});

test("executor: unknown tool in explicit plan is rejected", async () => {
  const { callTool } = makeCtx();
  await assert.rejects(
    () => callTool("agent_create_plan", { goal: "x", steps: [{ title: "bad", tool: "nope_tool" }] }),
    /Unknown tool/
  );
});

test("luau analyzer: catches unknown service, deprecated wait, unclosed delimiter", () => {
  const issues = analyzeLuau('local x = game:GetService("NopeService")\nwait(1)\nlocal t = {', "test.luau");
  const codes = issues.map((i) => i.code);
  assert.ok(codes.includes("LUAU_UNKNOWN_SERVICE"));
  assert.ok(codes.includes("LUAU_DEPRECATED_WAIT"));
  assert.ok(codes.includes("LUAU_UNCLOSED"));
  const clean = analyzeLuau("--!strict\nlocal Players = game:GetService(\"Players\")\nprint(Players)", "ok.luau");
  assert.equal(clean.filter((i) => i.severity === "error").length, 0);
});

test("file tools: create/read/update with backup, search", async () => {
  const { callTool, cfg } = makeCtx();
  await callTool("file_create", { path: "hello.luau", content: "--!strict\nprint('hi')" });
  const read = await callTool("file_read", { path: "hello.luau" });
  assert.equal(read.totalLines, 2);
  const upd = await callTool("file_update", { path: "hello.luau", content: "--!strict\nprint('v2')" });
  assert.ok(upd.backup);
  const search = await callTool("file_search", { pattern: "print", glob: ".luau" });
  assert.equal(search.count, 1);
  await assert.rejects(() => callTool("file_read", { path: "../secret.txt" }), /escapes/);
  void cfg;
});

test("plugins: list + diagnose example connector", async () => {
  const { callTool } = makeCtx();
  const list = await callTool("plugin_list", {});
  assert.ok(Array.isArray(list));
  // Point at the real plugins dir via a fresh registry check of listConnectors.
  const real = listConnectors(join(process.cwd(), "plugins"));
  assert.ok(real.some((c) => c.manifest?.name === "example-connector"));
});

test("mcp protocol: initialize + tools/list + tools/call over in-memory transport", async () => {
  const { cfg, reg, db, callTool } = makeCtx();
  const server = buildMcpServer(cfg, reg, db, callTool);
  const client = new Client({ name: "test-client", version: "1.0.0" }, { capabilities: {} });
  const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
  await Promise.all([server.connect(serverTransport), client.connect(clientTransport)]);

  const tools = await client.listTools();
  assert.ok(tools.tools.length >= 10);
  assert.ok(tools.tools.some((t) => t.name === "file_read"));
  assert.ok(tools.tools.every((t) => t.inputSchema && typeof t.inputSchema === "object"));

  const resources = await client.listResources();
  assert.ok(resources.resources.some((r) => r.uri === "omnibridge://tools/catalogue"));

  const prompts = await client.listPrompts();
  assert.ok(prompts.prompts.some((p) => p.name === "roblox-game-mission"));

  const result = await client.callTool({ name: "file_list", arguments: { path: "." } });
  assert.equal(result.isError ?? false, false);
  assert.ok(result.content[0].text.includes("count"));

  const bad = await client.callTool({ name: "file_read", arguments: { path: "../escape.txt" } });
  assert.equal(bad.isError, true);

  await client.close();
  await server.close();
});
