import type { ToolDef } from "./permissions.js";
import { log } from "./logger.js";

/** Central tool registry: every module registers here; the MCP layer exposes all. */
export class Registry {
  private tools = new Map<string, ToolDef>();

  register(tool: ToolDef): void {
    if (this.tools.has(tool.name)) throw new Error(`Duplicate tool: ${tool.name}`);
    this.tools.set(tool.name, tool);
    log.debug("tool registered", { tool: tool.name, category: tool.category, level: tool.level });
  }

  get(name: string): ToolDef | undefined { return this.tools.get(name); }
  list(): ToolDef[] { return [...this.tools.values()].sort((a, b) => a.name.localeCompare(b.name)); }
  categories(): Record<string, string[]> {
    const out: Record<string, string[]> = {};
    for (const t of this.list()) (out[t.category] ??= []).push(t.name);
    return out;
  }
  get size(): number { return this.tools.size; }
}
