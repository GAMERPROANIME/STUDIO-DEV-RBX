#!/usr/bin/env node
/**
 * OMNIBRIDGE Desktop Bridge — Native Messaging host.
 * Chrome/Firefox launch this host and speak length-prefixed JSON
 * (4-byte little-endian length + UTF-8 JSON) on stdin/stdout.
 * The host forwards commands to the local OMNIBRIDGE server bridge API
 * and returns results. It NEVER executes arbitrary system commands:
 * only the fixed command set below is accepted.
 */
import { spawn } from "node:child_process";
import { readFileSync, existsSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

const SERVER = process.env.OMNIBRIDGE_SERVER ?? "http://127.0.0.1:8765";
const ALLOWED_COMMANDS = new Set([
  "get_active_tab", "get_page_content", "get_selected_text",
  "get_links", "search_page", "capture_page", "system_diagnostics",
]);

function token() {
  const p = join(homedir(), ".omnibridge", "token.txt");
  return existsSync(p) ? readFileSync(p, "utf8").trim() : "";
}

async function forward(command) {
  if (!ALLOWED_COMMANDS.has(command.type)) {
    return { requestId: command.requestId, ok: false, data: `Command not allowed: ${command.type}` };
  }
  // The extension executes browser commands; the host only relays via the
  // server's bridge result channel is not applicable here, so we expose
  // diagnostics + a health probe. Browser commands go through the HTTP
  // long-poll path (background.js). This host provides system diagnostics.
  if (command.type === "system_diagnostics") {
    const res = await fetch(`${SERVER}/api/health`, { headers: { Authorization: `Bearer ${token()}` } });
    const data = await res.json();
    return { requestId: command.requestId, ok: true, data };
  }
  return { requestId: command.requestId, ok: false, data: "Use the HTTP bridge path for browser commands (see extension/background.js)." };
}

let buffer = Buffer.alloc(0);
process.stdin.on("data", (chunk) => {
  buffer = Buffer.concat([buffer, chunk]);
  while (buffer.length >= 4) {
    const len = buffer.readUInt32LE(0);
    if (buffer.length < 4 + len) break;
    const msg = JSON.parse(buffer.subarray(4, 4 + len).toString("utf8"));
    buffer = buffer.subarray(4 + len);
    forward(msg).then((result) => {
      const payload = Buffer.from(JSON.stringify(result), "utf8");
      const header = Buffer.alloc(4);
      header.writeUInt32LE(payload.length, 0);
      process.stdout.write(Buffer.concat([header, payload]));
    }).catch((e) => {
      const payload = Buffer.from(JSON.stringify({ requestId: msg.requestId, ok: false, data: String(e) }), "utf8");
      const header = Buffer.alloc(4);
      header.writeUInt32LE(payload.length, 0);
      process.stdout.write(Buffer.concat([header, payload]));
    });
  }
});

// Keep-alive: the host exits when stdin closes (browser disconnects).
process.stdin.on("end", () => process.exit(0));
void spawn;
