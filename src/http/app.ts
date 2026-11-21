import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import { existsSync, readFileSync } from "node:fs";
import { join, extname } from "node:path";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import { isInitializeRequest } from "@modelcontextprotocol/sdk/types.js";
import { randomUUID } from "node:crypto";
import type { OmniBridgeConfig } from "../config.js";
import type { Registry } from "../core/registry.js";
import type { Db } from "../core/db.js";
import type { BrowserBridge } from "../browser/bridge.js";
import type { TaskExecutor } from "../agent/executor.js";
import type { KnowledgeEngine } from "../knowledge/engine.js";
import type { RobloxConnector } from "../roblox/connector.js";
import { buildMcpServer } from "../mcp/server.js";
import { log } from "../core/logger.js";

const MIME: Record<string, string> = {
  ".html": "text/html", ".js": "text/javascript", ".css": "text/css",
  ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon",
};

function sendJson(res: ServerResponse, status: number, obj: unknown): void {
  const body = JSON.stringify(obj);
  res.writeHead(status, { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(body) });
  res.end(body);
}

function readBody(req: IncomingMessage): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    req.on("data", (c) => chunks.push(c as Buffer));
    req.on("end", () => {
      const text = Buffer.concat(chunks).toString("utf8");
      if (!text) return resolve(undefined);
      try { resolve(JSON.parse(text)); } catch (e) { reject(e); }
    });
    req.on("error", reject);
  });
}

export interface HttpDeps {
  cfg: OmniBridgeConfig;
  reg: Registry;
  db: Db;
  bridge: BrowserBridge;
  executor: TaskExecutor;
  knowledge: KnowledgeEngine;
  roblox: RobloxConnector;
  callTool: (name: string, args: Record<string, unknown>, confirmed?: boolean) => Promise<unknown>;
}

/**
 * HTTP server: Streamable HTTP MCP endpoint (/mcp), dashboard API (/api/*),
 * browser bridge endpoints (/bridge/*), static dashboard (/).
 * Binds to 127.0.0.1 by default — never exposed externally without auth.
 */
export function startHttpServer(deps: HttpDeps): ReturnType<typeof createServer> {
  const { cfg } = deps;
  // Stateful MCP sessions (one transport per session).
  const transports: Record<string, StreamableHTTPServerTransport> = {};

  const server = createServer(async (req, res) => {
    const url = new URL(req.url ?? "/", `http://${req.headers.host ?? "localhost"}`);
    const path = url.pathname;

    // ---- MCP Streamable HTTP ----
    if (path === "/mcp") {
      // Origin check (DNS-rebinding protection).
      const origin = req.headers.origin;
      if (origin && !/^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(origin)) {
        return sendJson(res, 403, { error: "Forbidden origin" });
      }
      if (cfg.requireToken) {
        const auth = req.headers.authorization ?? "";
        if (auth !== `Bearer ${cfg.token}`) return sendJson(res, 401, { error: "Unauthorized — provide Bearer token (see ~/.omnibridge/token.txt)" });
      }
      try {
        const body = req.method === "POST" ? await readBody(req) : undefined;
        const sessionId = req.headers["mcp-session-id"] as string | undefined;
        let transport: StreamableHTTPServerTransport | undefined;
        if (sessionId && transports[sessionId]) {
          transport = transports[sessionId];
        } else if (!sessionId && req.method === "POST" && isInitializeRequest(body)) {
          transport = new StreamableHTTPServerTransport({
            sessionIdGenerator: () => randomUUID(),
            onsessioninitialized: (sid) => { transports[sid] = transport!; },
          });
          transport.onclose = () => { if (transport!.sessionId) delete transports[transport!.sessionId]; };
          const mcp = buildMcpServer(cfg, deps.reg, deps.db, deps.callTool);
          await mcp.connect(transport);
        } else if (!sessionId) {
          return sendJson(res, 400, { jsonrpc: "2.0", error: { code: -32000, message: "Bad Request: No valid session ID" }, id: null });
        }
        await transport!.handleRequest(req, res, body);
      } catch (e) {
        log.error("mcp http error", { error: String(e) });
        if (!res.headersSent) sendJson(res, 500, { jsonrpc: "2.0", error: { code: -32603, message: "Internal error" }, id: null });
      }
      return;
    }

    // ---- Browser bridge ----
    if (path === "/bridge/register" && req.method === "POST") {
      const body = (await readBody(req)) as { clientId?: string; info?: Record<string, unknown> };
      const clientId = body.clientId ?? randomUUID();
      deps.bridge.register(clientId, body.info ?? {});
      return sendJson(res, 200, { ok: true, clientId });
    }
    if (path === "/bridge/poll" && req.method === "GET") {
      const clientId = url.searchParams.get("clientId") ?? "";
      const cmd = await deps.bridge.poll(clientId, 25_000);
      return sendJson(res, 200, { command: cmd });
    }
    if (path === "/bridge/result" && req.method === "POST") {
      const body = (await readBody(req)) as { requestId?: string; ok?: boolean; data?: unknown };
      const accepted = body.requestId ? deps.bridge.submitResult(body.requestId, Boolean(body.ok), body.data) : false;
      return sendJson(res, 200, { ok: accepted });
    }

    // ---- Dashboard API ----
    if (path.startsWith("/api/")) {
      if (cfg.requireToken) {
        const auth = req.headers.authorization ?? "";
        const token = url.searchParams.get("token") ?? "";
        if (auth !== `Bearer ${cfg.token}` && token !== cfg.token) {
          return sendJson(res, 401, { error: "Unauthorized" });
        }
      }
      return handleApi(req, res, url, deps);
    }

    // ---- Static dashboard ----
    const filePath = path === "/" ? join(cfg.dashboardDir, "index.html") : join(cfg.dashboardDir, path);
    if (existsSync(filePath) && !filePath.includes("..")) {
      const data = readFileSync(filePath);
      res.writeHead(200, { "Content-Type": MIME[extname(filePath)] ?? "application/octet-stream" });
      return res.end(data);
    }
    sendJson(res, 404, { error: "Not found" });
  });

  server.listen(cfg.httpPort, cfg.httpHost, () => {
    log.info("http server listening", { host: cfg.httpHost, port: cfg.httpPort, mcp: `http://${cfg.httpHost}:${cfg.httpPort}/mcp`, dashboard: `http://${cfg.httpHost}:${cfg.httpPort}/` });
  });
  return server;
}

async function handleApi(req: IncomingMessage, res: ServerResponse, url: URL, deps: HttpDeps): Promise<void> {
  const { cfg, reg, db } = deps;
  const path = url.pathname;
  try {
    if (path === "/api/health" && req.method === "GET") {
      const roblox = await deps.roblox.info();
      return sendJson(res, 200, {
        ok: true, version: "1.0.0", toolCount: reg.size, categories: reg.categories(),
        permissionLevel: cfg.permissionLevel, transport: cfg.transport,
        roblox: { available: roblox.available, tools: roblox.tools, error: roblox.error },
        bridge: deps.bridge.status(), knowledge: deps.knowledge.stats(),
      });
    }
    if (path === "/api/tools" && req.method === "GET") {
      return sendJson(res, 200, reg.list().map((t) => ({ name: t.name, category: t.category, level: t.level, readOnly: t.readOnly, description: t.description })));
    }
    if (path === "/api/tasks" && req.method === "GET") return sendJson(res, 200, deps.executor.listTasks(50));
    if (path.startsWith("/api/tasks/") && req.method === "GET") {
      const id = decodeURIComponent(path.slice("/api/tasks/".length));
      const task = deps.executor.getTask(id);
      return task ? sendJson(res, 200, task) : sendJson(res, 404, { error: "Task not found" });
    }
    if (path === "/api/audit" && req.method === "GET") return sendJson(res, 200, db.auditRecent(100));
    if (path === "/api/knowledge" && req.method === "GET") return sendJson(res, 200, deps.knowledge.stats());
    if (path === "/api/call" && req.method === "POST") {
      const body = (await readBody(req)) as { tool?: string; args?: Record<string, unknown>; confirm?: boolean };
      if (!body.tool) return sendJson(res, 400, { error: "tool required" });
      const result = await deps.callTool(body.tool, body.args ?? {}, Boolean(body.confirm));
      return sendJson(res, 200, { ok: true, result });
    }
    sendJson(res, 404, { error: "Unknown API route" });
  } catch (e) {
    sendJson(res, 500, { error: e instanceof Error ? e.message : String(e) });
  }
}
