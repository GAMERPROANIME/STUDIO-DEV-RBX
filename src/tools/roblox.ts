import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join, extname } from "node:path";
import type { Registry } from "../core/registry.js";
import type { ToolDef } from "../core/permissions.js";
import type { RobloxConnector } from "../roblox/connector.js";
import { STUDIO_SETUP_INSTRUCTIONS } from "../roblox/connector.js";
import { sandboxResolve } from "../core/sandbox.js";
import { analyzeLuau } from "../roblox/luau.js";

/**
 * Roblox Studio tools. Two layers:
 *  1. Official Studio MCP proxy (live Studio): list/get state, inspect,
 *     scripts, console, playtest, capture — delegated to Roblox's own server.
 *  2. Local Rojo/file layer (works without Studio): project inspection,
 *     script read/search/edit on disk.
 * Every tool states which layer it uses. Nothing is simulated.
 */
export function registerRobloxTools(reg: Registry, connector: RobloxConnector): void {
  const tools: ToolDef[] = [
    {
      name: "roblox_list_studios",
      description: "List open Roblox Studio instances via the official Studio MCP server. If Studio MCP is not configured, returns available=false with exact setup instructions (never fakes a list).",
      inputSchema: { type: "object", properties: {} },
      level: 1, category: "roblox", readOnly: true,
      handler: async () => {
        const info = await connector.info();
        if (!info.available) return { available: false, error: info.error, setupInstructions: info.setupInstructions };
        // Delegate to the official server's own listing tool when present.
        const listTool = info.tools.find((t) => /list.*studio|studio.*list/i.test(t));
        let studios: unknown = null;
        if (listTool) {
          try { studios = await connector.callTool(listTool, {}); } catch { studios = null; }
        }
        return { available: true, command: info.command, officialTools: info.tools, studios };
      },
    },
    {
      name: "roblox_get_studio_state",
      description: "Get the state of the connected Studio instance (open place, selection, playtest status) via the official Studio MCP server.",
      inputSchema: { type: "object", properties: {} },
      level: 1, category: "roblox", readOnly: true,
      handler: async () => {
        const info = await connector.info();
        if (!info.available) return { available: false, setupInstructions: info.setupInstructions };
        const stateTool = info.tools.find((t) => /state|status/i.test(t));
        if (!stateTool) return { available: true, note: "Connected, but the official server exposes no state tool.", officialTools: info.tools };
        return { available: true, state: await connector.callTool(stateTool, {}) };
      },
    },
    {
      name: "roblox_inspect_project",
      description: "Inspect a Roblox/Rojo project on disk: project.json tree, .luau/.lua/.rbxlx files, services layout (ServerScriptService, ReplicatedStorage…). Works without Studio running.",
      inputSchema: { type: "object", properties: { path: { type: "string", default: "." } } },
      level: 1, category: "roblox", readOnly: true,
      handler: (args, ctx) => {
        const abs = sandboxResolve(ctx.config.workspaceRoot, String(args.path ?? "."));
        const readJson = (n: string) => { try { return JSON.parse(readFileSync(join(abs, n), "utf8")); } catch { return null; } };
        const project = readJson("project.json") ?? readJson("default.project.json");
        const luau: string[] = [];
        const walk = (dir: string, depth: number) => {
          if (depth > 6) return;
          let entries: string[] = [];
          try { entries = readdirSync(dir); } catch { return; }
          for (const e of entries.sort()) {
            if (e === "node_modules" || e === ".git") continue;
            const full = join(dir, e);
            try {
              if (statSync(full).isDirectory()) walk(full, depth + 1);
              else if ([".luau", ".lua", ".rbxlx", ".rbxl", ".rbxm", ".json"].includes(extname(e).toLowerCase())) {
                luau.push(full.slice(abs.length + 1));
              }
            } catch { /* ignore */ }
          }
        };
        walk(abs, 0);
        return { path: String(args.path ?? "."), hasRojoProject: Boolean(project), project, files: luau.slice(0, 500), fileCount: luau.length };
      },
    },
    {
      name: "roblox_search_scripts",
      description: "Search Luau script contents in a Rojo project on disk (regex). Returns file, line and snippet.",
      inputSchema: { type: "object", properties: { pattern: { type: "string" }, path: { type: "string", default: "." }, maxResults: { type: "integer", minimum: 1, maximum: 500, default: 100 } }, required: ["pattern"] },
      level: 1, category: "roblox", readOnly: true,
      handler: (args, ctx) => {
        const abs = sandboxResolve(ctx.config.workspaceRoot, String(args.path ?? "."));
        const re = new RegExp(String(args.pattern), "i");
        const hits: Array<Record<string, unknown>> = [];
        const walk = (dir: string, depth: number) => {
          if (depth > 6 || hits.length >= Number(args.maxResults ?? 100)) return;
          let entries: string[] = [];
          try { entries = readdirSync(dir); } catch { return; }
          for (const e of entries.sort()) {
            if (e === "node_modules" || e === ".git") continue;
            const full = join(dir, e);
            try {
              if (statSync(full).isDirectory()) walk(full, depth + 1);
              else if (e.endsWith(".luau") || e.endsWith(".lua")) {
                readFileSync(full, "utf8").split("\n").forEach((line, i) => {
                  if (hits.length < Number(args.maxResults ?? 100) && re.test(line)) {
                    hits.push({ file: full.slice(abs.length + 1), line: i + 1, text: line.trim().slice(0, 300) });
                  }
                });
              }
            } catch { /* ignore */ }
          }
        };
        walk(abs, 0);
        return { pattern: String(args.pattern), count: hits.length, hits };
      },
    },
    {
      name: "roblox_read_script",
      description: "Read a Luau script file from a Rojo project on disk, with static analysis attached.",
      inputSchema: { type: "object", properties: { path: { type: "string" } }, required: ["path"] },
      level: 1, category: "roblox", readOnly: true,
      handler: (args, ctx) => {
        const abs = sandboxResolve(ctx.config.workspaceRoot, String(args.path));
        const src = readFileSync(abs, "utf8");
        return { path: String(args.path), lines: src.split("\n").length, source: src.slice(0, 100_000), analysis: analyzeLuau(src, String(args.path)) };
      },
    },
    {
      name: "roblox_inspect_instance",
      description: "Inspect a live instance in Studio via the official MCP server (class, properties, parent path). Requires Studio MCP configured; otherwise returns setup instructions.",
      inputSchema: { type: "object", properties: { path: { type: "string", description: "Instance path e.g. game.Workspace.Part" } }, required: ["path"] },
      level: 1, category: "roblox", readOnly: true,
      handler: async (args) => {
        const info = await connector.info();
        if (!info.available) return { available: false, setupInstructions: info.setupInstructions };
        const tool = info.tools.find((t) => /inspect|get.*instance|instance/i.test(t));
        if (!tool) return { available: true, error: "Official server has no instance-inspection tool.", officialTools: info.tools };
        return { available: true, instance: await connector.callTool(tool, { path: String(args.path) }) };
      },
    },
    {
      name: "roblox_execute_luau",
      description: "Execute Luau code in the live Studio session via the official MCP server (plugin security context). Requires Studio MCP configured.",
      inputSchema: { type: "object", properties: { code: { type: "string" } }, required: ["code"] },
      level: 3, category: "roblox", readOnly: false,
      handler: async (args) => {
        const info = await connector.info();
        if (!info.available) return { available: false, setupInstructions: info.setupInstructions };
        const tool = info.tools.find((t) => /execute|run.*code|eval/i.test(t));
        if (!tool) return { available: true, error: "Official server has no code-execution tool.", officialTools: info.tools };
        return { available: true, result: await connector.callTool(tool, { code: String(args.code) }) };
      },
    },
    {
      name: "roblox_edit_scripts",
      description: "Edit Luau scripts on disk (Rojo project): create or overwrite script files with backup. For live Studio editing, use the official MCP server tools via roblox_execute_luau.",
      inputSchema: { type: "object", properties: { path: { type: "string" }, content: { type: "string" } }, required: ["path", "content"] },
      level: 3, category: "roblox", readOnly: false,
      handler: async (args, ctx) => {
        const result = (await ctx.callTool("file_update", { path: String(args.path), content: String(args.content) })) as Record<string, unknown>;
        const issues = analyzeLuau(String(args.content), String(args.path));
        return { ...result, analysis: issues, errorCount: issues.filter((i) => i.severity === "error").length };
      },
    },
    {
      name: "roblox_create_objects",
      description: "Create instances in the live Studio session via the official MCP server (e.g. Part, Folder, RemoteEvent under a parent). Requires Studio MCP configured.",
      inputSchema: { type: "object", properties: { className: { type: "string" }, parent: { type: "string" }, properties: { type: "object", default: {} } }, required: ["className", "parent"] },
      level: 3, category: "roblox", readOnly: false,
      handler: async (args) => {
        const info = await connector.info();
        if (!info.available) return { available: false, setupInstructions: info.setupInstructions };
        const tool = info.tools.find((t) => /create.*object|insert/i.test(t));
        if (!tool) return { available: true, error: "Official server has no object-creation tool.", officialTools: info.tools };
        return { available: true, result: await connector.callTool(tool, { className: String(args.className), parent: String(args.parent), properties: args.properties ?? {} }) };
      },
    },
    {
      name: "roblox_playtest",
      description: "Start/stop a playtest in Studio via the official MCP server and return its status. Requires Studio MCP configured.",
      inputSchema: { type: "object", properties: { action: { type: "string", enum: ["start", "stop", "status"], default: "status" } } },
      level: 3, category: "roblox", readOnly: false,
      handler: async (args) => {
        const info = await connector.info();
        if (!info.available) return { available: false, setupInstructions: info.setupInstructions };
        const tool = info.tools.find((t) => /playtest|test/i.test(t));
        if (!tool) return { available: true, error: "Official server has no playtest tool.", officialTools: info.tools };
        return { available: true, result: await connector.callTool(tool, { action: String(args.action ?? "status") }) };
      },
    },
    {
      name: "roblox_get_console_output",
      description: "Read Studio console output (errors/warnings) via the official MCP server. Requires Studio MCP configured.",
      inputSchema: { type: "object", properties: { limit: { type: "integer", minimum: 1, maximum: 500, default: 100 } } },
      level: 1, category: "roblox", readOnly: true,
      handler: async (args) => {
        const info = await connector.info();
        if (!info.available) return { available: false, setupInstructions: info.setupInstructions };
        const tool = info.tools.find((t) => /console|output|log/i.test(t));
        if (!tool) return { available: true, error: "Official server has no console tool.", officialTools: info.tools };
        return { available: true, output: await connector.callTool(tool, { limit: Number(args.limit ?? 100) }) };
      },
    },
    {
      name: "roblox_capture_screen",
      description: "Capture a screenshot of the Studio viewport via the official MCP server. Requires Studio MCP configured.",
      inputSchema: { type: "object", properties: {} },
      level: 1, category: "roblox", readOnly: true,
      handler: async () => {
        const info = await connector.info();
        if (!info.available) return { available: false, setupInstructions: info.setupInstructions };
        const tool = info.tools.find((t) => /capture|screenshot|screen/i.test(t));
        if (!tool) return { available: true, error: "Official server has no capture tool.", officialTools: info.tools };
        return { available: true, capture: await connector.callTool(tool, {}) };
      },
    },
    {
      name: "roblox_search_assets",
      description: "Search the Roblox Creator Store for assets (models, plugins) via the official MCP server when available. Otherwise returns setup instructions — never fakes results.",
      inputSchema: { type: "object", properties: { query: { type: "string" }, assetType: { type: "string", default: "Model" } }, required: ["query"] },
      level: 1, category: "roblox", readOnly: true,
      handler: async (args) => {
        const info = await connector.info();
        if (!info.available) return { available: false, setupInstructions: info.setupInstructions };
        const tool = info.tools.find((t) => /asset|store|search/i.test(t));
        if (!tool) return { available: true, error: "Official server has no asset-search tool.", officialTools: info.tools };
        return { available: true, results: await connector.callTool(tool, { query: String(args.query), assetType: String(args.assetType ?? "Model") }) };
      },
    },
  ];
  for (const t of tools) reg.register(t);
  void existsSync;
}
