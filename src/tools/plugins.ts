import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import type { Registry } from "../core/registry.js";
import type { ToolDef } from "../core/permissions.js";

/**
 * Plugin/connector manager. A connector is a directory under plugins/ with a
 * manifest.json: { name, version, author, description, capabilities, tools,
 * permissions, enabled }. Tools declared by a connector are NOT auto-executed
 * — the manager validates the manifest and reports compatibility. Connectors
 * that ship real code register their tools programmatically (see
 * plugins/example-connector). A connector can never gain permissions beyond
 * its manifest.
 */
export interface ConnectorManifest {
  name: string;
  version: string;
  author?: string;
  description?: string;
  capabilities?: string[];
  tools?: string[];
  permissions?: number[];
  enabled?: boolean;
  [k: string]: unknown;
}

export function listConnectors(pluginsDir: string): Array<{ dir: string; manifest: ConnectorManifest | null; error?: string }> {
  if (!existsSync(pluginsDir)) return [];
  const out: Array<{ dir: string; manifest: ConnectorManifest | null; error?: string }> = [];
  for (const entry of readdirSync(pluginsDir).sort()) {
    const dir = join(pluginsDir, entry);
    if (!statSync(dir).isDirectory()) continue;
    const manifestPath = join(dir, "manifest.json");
    if (!existsSync(manifestPath)) { out.push({ dir: entry, manifest: null, error: "missing manifest.json" }); continue; }
    try {
      const manifest = JSON.parse(readFileSync(manifestPath, "utf8")) as ConnectorManifest;
      if (!manifest.name || !manifest.version) throw new Error("manifest requires name and version");
      out.push({ dir: entry, manifest });
    } catch (e) {
      out.push({ dir: entry, manifest: null, error: e instanceof Error ? e.message : String(e) });
    }
  }
  return out;
}

export function registerPluginTools(reg: Registry): void {
  const tools: ToolDef[] = [
    {
      name: "plugin_list",
      description: "List installed connectors/plugins with their manifests, capabilities and enabled state.",
      inputSchema: { type: "object", properties: {} },
      level: 1, category: "plugins", readOnly: true,
      handler: (_args, ctx) => listConnectors(ctx.config.pluginsDir),
    },
    {
      name: "plugin_diagnose",
      description: "Diagnose a connector: validates its manifest, checks declared tools exist in the registry, and reports permission requirements.",
      inputSchema: { type: "object", properties: { name: { type: "string" } }, required: ["name"] },
      level: 1, category: "plugins", readOnly: true,
      handler: (args, ctx) => {
        const connectors = listConnectors(ctx.config.pluginsDir);
        const found = connectors.find((c) => c.manifest?.name === String(args.name) || c.dir === String(args.name));
        if (!found) throw new Error(`Connector not found: ${args.name}`);
        if (!found.manifest) return { name: String(args.name), ok: false, error: found.error };
        const declared = found.manifest.tools ?? [];
        const missing = declared.filter((t) => !reg.get(t));
        return {
          name: found.manifest.name, ok: missing.length === 0,
          version: found.manifest.version, enabled: found.manifest.enabled !== false,
          capabilities: found.manifest.capabilities ?? [],
          declaredTools: declared, missingTools: missing,
          permissions: found.manifest.permissions ?? [],
          note: "A connector never gains permissions beyond its manifest.",
        };
      },
    },
  ];
  for (const t of tools) reg.register(t);
}
