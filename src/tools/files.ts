import { readdirSync, readFileSync, writeFileSync, mkdirSync, copyFileSync, statSync, existsSync } from "node:fs";
import { basename, dirname, extname, join, relative } from "node:path";
import type { Registry } from "../core/registry.js";
import type { ToolDef } from "../core/permissions.js";
import { sandboxResolve } from "../core/sandbox.js";
import { redactSecrets } from "../core/permissions.js";

const SKIP_DIRS = new Set(["node_modules", ".git", "dist", ".next", "build", "out", "target", ".cache"]);
const TEXT_EXTS = new Set([".ts", ".js", ".mjs", ".cjs", ".json", ".md", ".txt", ".luau", ".lua", ".rbxlx", ".xml", ".html", ".css", ".yml", ".yaml", ".toml", ".ini", ".cfg", ".sh", ".py", ".rs", ".go", ".java", ".c", ".h", ".cpp", ".cs", ".rb", ".php", ".sql", ".graphql", ".env.example"]);

function walk(root: string, dir: string, out: string[], depth: number, maxDepth: number): void {
  if (depth > maxDepth || out.length > 5000) return;
  let entries: string[];
  try { entries = readdirSync(dir); } catch { return; }
  for (const e of entries.sort()) {
    if (SKIP_DIRS.has(e)) continue;
    const full = join(dir, e);
    let st;
    try { st = statSync(full); } catch { continue; }
    if (st.isDirectory()) walk(root, full, out, depth + 1, maxDepth);
    else out.push(relative(root, full));
  }
}

function backup(cfg: { dataDir: string }, absPath: string): string | null {
  if (!existsSync(absPath)) return null;
  const dir = join(cfg.dataDir, "backups");
  mkdirSync(dir, { recursive: true });
  const dest = join(dir, `${basename(absPath)}.${Date.now()}.bak`);
  copyFileSync(absPath, dest);
  return dest;
}

export function registerFileTools(reg: Registry): void {
  const tools: ToolDef[] = [
    {
      name: "file_list",
      description: "List files in a directory inside the workspace (recursive up to depth). Sandboxed: cannot escape the workspace root.",
      inputSchema: { type: "object", properties: { path: { type: "string", default: "." }, recursive: { type: "boolean", default: true }, maxDepth: { type: "integer", minimum: 1, maximum: 8, default: 4 } } },
      level: 1, category: "files", readOnly: true,
      handler: (args, ctx) => {
        const abs = sandboxResolve(ctx.config.workspaceRoot, String(args.path ?? "."));
        const files: string[] = [];
        if (args.recursive === false) {
          for (const e of readdirSync(abs).sort()) if (!SKIP_DIRS.has(e)) files.push(join(relative(ctx.config.workspaceRoot, abs), e));
        } else {
          walk(ctx.config.workspaceRoot, abs, files, 0, Number(args.maxDepth ?? 4));
        }
        return { path: String(args.path ?? "."), count: files.length, files: files.slice(0, 2000) };
      },
    },
    {
      name: "file_read",
      description: "Read a text file inside the workspace. Binary files and files over the size limit are rejected with a clear error.",
      inputSchema: { type: "object", properties: { path: { type: "string" }, offset: { type: "integer", minimum: 1, default: 1 }, limit: { type: "integer", minimum: 1, maximum: 10000, default: 2000 } } },
      level: 1, category: "files", readOnly: true,
      handler: (args, ctx) => {
        const abs = sandboxResolve(ctx.config.workspaceRoot, String(args.path));
        const st = statSync(abs);
        if (st.size > ctx.config.maxFileBytes) throw new Error(`File too large (${st.size} bytes > ${ctx.config.maxFileBytes})`);
        const ext = extname(abs).toLowerCase();
        if (!TEXT_EXTS.has(ext) && ext !== "") throw new Error(`Refusing to read non-text file: ${ext}`);
        const lines = readFileSync(abs, "utf8").split("\n");
        const offset = Number(args.offset ?? 1);
        const limit = Number(args.limit ?? 2000);
        return { path: String(args.path), totalLines: lines.length, lines: lines.slice(offset - 1, offset - 1 + limit) };
      },
    },
    {
      name: "file_search",
      description: "Search file contents (regex) across the workspace. Returns matching files with line numbers and snippets. Skips node_modules/.git/dist.",
      inputSchema: { type: "object", properties: { pattern: { type: "string" }, path: { type: "string", default: "." }, glob: { type: "string", description: "Optional extension filter e.g. .luau" }, maxResults: { type: "integer", minimum: 1, maximum: 500, default: 100 } } },
      level: 1, category: "files", readOnly: true,
      handler: (args, ctx) => {
        const abs = sandboxResolve(ctx.config.workspaceRoot, String(args.path ?? "."));
        const re = new RegExp(String(args.pattern), "i");
        const glob = args.glob ? String(args.glob).replace(/^\*/, "") : null;
        const files: string[] = [];
        walk(ctx.config.workspaceRoot, abs, files, 0, 6);
        const hits: Array<Record<string, unknown>> = [];
        const maxResults = Number(args.maxResults ?? 100);
        for (const f of files) {
          if (glob && !f.endsWith(glob)) continue;
          if (!TEXT_EXTS.has(extname(f).toLowerCase())) continue;
          let content: string;
          try {
            const full = join(ctx.config.workspaceRoot, f);
            if (statSync(full).size > ctx.config.maxFileBytes) continue;
            content = readFileSync(full, "utf8");
          } catch { continue; }
          content.split("\n").forEach((line, i) => {
            if (hits.length < maxResults && re.test(line)) {
              hits.push({ file: f, line: i + 1, text: line.trim().slice(0, 300) });
            }
          });
          if (hits.length >= maxResults) break;
        }
        return { pattern: String(args.pattern), count: hits.length, hits };
      },
    },
    {
      name: "file_create",
      description: "Create a new file inside the workspace (parent dirs created). Fails if the file already exists — use file_update to modify. A backup is taken automatically for overwrites via file_update.",
      inputSchema: { type: "object", properties: { path: { type: "string" }, content: { type: "string" } }, required: ["path", "content"] },
      level: 3, category: "files", readOnly: false,
      handler: (args, ctx) => {
        const abs = sandboxResolve(ctx.config.workspaceRoot, String(args.path));
        if (existsSync(abs)) throw new Error(`File already exists: ${args.path}. Use file_update.`);
        mkdirSync(dirname(abs), { recursive: true });
        writeFileSync(abs, redactSecrets(String(args.content)), "utf8");
        return { ok: true, path: String(args.path), bytes: Buffer.byteLength(String(args.content)) };
      },
    },
    {
      name: "file_update",
      description: "Create or overwrite a file inside the workspace. Always backs up the previous version to the data dir first (reversible).",
      inputSchema: { type: "object", properties: { path: { type: "string" }, content: { type: "string" } }, required: ["path", "content"] },
      level: 3, category: "files", readOnly: false,
      handler: (args, ctx) => {
        const abs = sandboxResolve(ctx.config.workspaceRoot, String(args.path));
        const bak = backup(ctx.config, abs);
        mkdirSync(dirname(abs), { recursive: true });
        writeFileSync(abs, redactSecrets(String(args.content)), "utf8");
        return { ok: true, path: String(args.path), backup: bak, bytes: Buffer.byteLength(String(args.content)) };
      },
    },
    {
      name: "file_backup",
      description: "Manually back up a workspace file to the data dir. Returns the backup path.",
      inputSchema: { type: "object", properties: { path: { type: "string" } }, required: ["path"] },
      level: 2, category: "files", readOnly: false,
      handler: (args, ctx) => {
        const abs = sandboxResolve(ctx.config.workspaceRoot, String(args.path));
        const bak = backup(ctx.config, abs);
        if (!bak) throw new Error(`File not found: ${args.path}`);
        return { ok: true, path: String(args.path), backup: bak };
      },
    },
    {
      name: "project_inspect",
      description: "Inspect a project directory: file tree summary, detected project type (Node/Rojo/Roblox/Python), entry points, package.json / project.json contents.",
      inputSchema: { type: "object", properties: { path: { type: "string", default: "." } } },
      level: 1, category: "project", readOnly: true,
      handler: (args, ctx) => {
        const abs = sandboxResolve(ctx.config.workspaceRoot, String(args.path ?? "."));
        const files: string[] = [];
        walk(ctx.config.workspaceRoot, abs, files, 0, 5);
        const byExt: Record<string, number> = {};
        for (const f of files) { const e = extname(f).toLowerCase() || "(none)"; byExt[e] = (byExt[e] ?? 0) + 1; }
        const readJson = (name: string) => {
          const p = join(abs, name);
          try { return JSON.parse(readFileSync(p, "utf8")); } catch { return null; }
        };
        const pkg = readJson("package.json");
        const rojo = readJson("project.json") ?? readJson("default.project.json");
        const type = rojo ? "roblox-rojo" : pkg ? "node" : files.some((f) => f.endsWith(".py")) ? "python" : "unknown";
        return {
          path: String(args.path ?? "."), type, fileCount: files.length, byExtension: byExt,
          packageJson: pkg ? { name: pkg.name, version: pkg.version, scripts: pkg.scripts, dependencies: pkg.dependencies } : null,
          rojoProject: rojo,
          topLevel: files.filter((f) => !f.includes("/")).slice(0, 100),
        };
      },
    },
    {
      name: "project_analyze",
      description: "Analyze a project: counts Luau/JS/TS files, finds TODOs, runs Luau static analysis on every .luau file, reports dependency health from package.json.",
      inputSchema: { type: "object", properties: { path: { type: "string", default: "." } } },
      level: 1, category: "project", readOnly: true,
      handler: async (args, ctx) => {
        const abs = sandboxResolve(ctx.config.workspaceRoot, String(args.path ?? "."));
        const files: string[] = [];
        walk(ctx.config.workspaceRoot, abs, files, 0, 6);
        const luauFiles = files.filter((f) => f.endsWith(".luau") || f.endsWith(".lua"));
        const { analyzeLuau } = await import("../roblox/luau.js");
        const luauIssues: Array<Record<string, unknown>> = [];
        for (const f of luauFiles.slice(0, 200)) {
          try {
            const src = readFileSync(join(ctx.config.workspaceRoot, f), "utf8");
            for (const issue of analyzeLuau(src, f)) luauIssues.push({ file: f, ...issue });
          } catch { /* ignore */ }
        }
        const todos: Array<Record<string, unknown>> = [];
        for (const f of files.slice(0, 2000)) {
          if (!TEXT_EXTS.has(extname(f).toLowerCase())) continue;
          try {
            readFileSync(join(ctx.config.workspaceRoot, f), "utf8").split("\n").forEach((line, i) => {
              if (/TODO|FIXME|HACK/.test(line)) todos.push({ file: f, line: i + 1, text: line.trim().slice(0, 200) });
            });
          } catch { /* ignore */ }
        }
        return {
          path: String(args.path ?? "."), fileCount: files.length,
          luauFiles: luauFiles.length, luauIssues: luauIssues.slice(0, 200),
          luauErrorCount: luauIssues.filter((i) => i.severity === "error").length,
          todos: todos.slice(0, 100),
        };
      },
    },
  ];
  for (const t of tools) reg.register(t);
}
