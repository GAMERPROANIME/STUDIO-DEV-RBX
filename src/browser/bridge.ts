import { randomUUID } from "node:crypto";
import { log } from "../core/logger.js";

/**
 * Browser extension bridge.
 * The MV3 extension connects over HTTP (long-poll) to this in-process hub:
 *  POST /bridge/register  {clientId, info}        → registers the extension
 *  GET  /bridge/poll?clientId=…                    → long-poll for commands
 *  POST /bridge/result  {requestId, ok, data|error} → returns a result
 * OMNIBRIDGE tools (browser_*) enqueue commands here and await results.
 * If no extension is connected, tools return an honest "not connected" error
 * — they never fabricate page content.
 */
export interface BridgeCommand {
  requestId: string;
  type: string;
  args: Record<string, unknown>;
}

interface Pending {
  resolve: (v: unknown) => void;
  reject: (e: Error) => void;
  timer: NodeJS.Timeout;
}

export class BrowserBridge {
  private clients = new Map<string, { info: Record<string, unknown>; connectedAt: string }>();
  private queue: BridgeCommand[] = [];
  private pending = new Map<string, Pending>();
  private pollWaiters: Array<{ clientId: string; resolve: (c: BridgeCommand | null) => void }> = [];

  register(clientId: string, info: Record<string, unknown>): void {
    this.clients.set(clientId, { info, connectedAt: new Date().toISOString() });
    log.info("browser extension connected", { clientId });
  }

  status(): { connected: boolean; clients: Array<{ clientId: string; info: Record<string, unknown>; connectedAt: string }> } {
    return { connected: this.clients.size > 0, clients: [...this.clients.entries()].map(([clientId, v]) => ({ clientId, ...v })) };
  }

  /** Long-poll: waits up to timeoutMs for the next command. */
  poll(clientId: string, timeoutMs = 25_000): Promise<BridgeCommand | null> {
    const next = this.queue.shift();
    if (next) return Promise.resolve(next);
    return new Promise((resolve) => {
      const waiter = { clientId, resolve };
      this.pollWaiters.push(waiter);
      setTimeout(() => {
        const i = this.pollWaiters.indexOf(waiter);
        if (i >= 0) { this.pollWaiters.splice(i, 1); resolve(null); }
      }, timeoutMs);
    });
  }

  submitResult(requestId: string, ok: boolean, data: unknown): boolean {
    const p = this.pending.get(requestId);
    if (!p) return false;
    clearTimeout(p.timer);
    this.pending.delete(requestId);
    if (ok) p.resolve(data); else p.reject(new Error(String(data)));
    return true;
  }

  /** Send a command to the extension and await its result. */
  async command(type: string, args: Record<string, unknown>, timeoutMs = 15_000): Promise<unknown> {
    if (this.clients.size === 0) {
      throw new Error(
        "Browser extension not connected. Load the extension from the extension/ folder " +
        "(chrome://extensions → Developer mode → Load unpacked) and open a page. " +
        "See docs/EXTENSION.md."
      );
    }
    const requestId = randomUUID();
    const cmd: BridgeCommand = { requestId, type, args };
    const waiterIdx = this.pollWaiters.findIndex((w) => this.clients.has(w.clientId));
    if (waiterIdx >= 0) {
      const [w] = this.pollWaiters.splice(waiterIdx, 1);
      w.resolve(cmd);
    } else {
      this.queue.push(cmd);
    }
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(requestId);
        reject(new Error(`Browser command '${type}' timed out after ${timeoutMs}ms`));
      }, timeoutMs);
      this.pending.set(requestId, { resolve, reject, timer });
    });
  }
}
