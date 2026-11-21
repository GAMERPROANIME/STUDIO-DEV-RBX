import type { Registry } from "../core/registry.js";
import type { ToolDef } from "../core/permissions.js";
import type { BrowserBridge } from "../browser/bridge.js";

/**
 * Browser tools — all delegated to the MV3 extension via the bridge.
 * When the extension is not connected they fail honestly (see bridge.ts).
 */
export function registerBrowserTools(reg: Registry, bridge: BrowserBridge): void {
  const tools: ToolDef[] = [
    {
      name: "browser_get_active_tab",
      description: "Get the active browser tab (URL, title) via the extension. Requires the OMNIBRIDGE extension connected.",
      inputSchema: { type: "object", properties: {} },
      level: 1, category: "browser", readOnly: true,
      handler: () => bridge.command("get_active_tab", {}),
    },
    {
      name: "browser_get_page_content",
      description: "Get the text content of the active page via the extension (user-authorized context). Requires the extension connected.",
      inputSchema: { type: "object", properties: { maxChars: { type: "integer", minimum: 500, maximum: 200000, default: 30000 } } },
      level: 1, category: "browser", readOnly: true,
      handler: (args) => bridge.command("get_page_content", { maxChars: Number(args.maxChars ?? 30000) }),
    },
    {
      name: "browser_get_selected_text",
      description: "Get the user's current text selection on the active page via the extension.",
      inputSchema: { type: "object", properties: {} },
      level: 1, category: "browser", readOnly: true,
      handler: () => bridge.command("get_selected_text", {}),
    },
    {
      name: "browser_get_links",
      description: "List links on the active page via the extension (href + text).",
      inputSchema: { type: "object", properties: { limit: { type: "integer", minimum: 1, maximum: 500, default: 100 } } },
      level: 1, category: "browser", readOnly: true,
      handler: (args) => bridge.command("get_links", { limit: Number(args.limit ?? 100) }),
    },
    {
      name: "browser_capture_page",
      description: "Capture a screenshot of the active tab via the extension (returns base64 PNG).",
      inputSchema: { type: "object", properties: {} },
      level: 1, category: "browser", readOnly: true,
      handler: () => bridge.command("capture_page", {}),
    },
    {
      name: "browser_search_page",
      description: "Search text within the active page via the extension. Returns matching snippets with context.",
      inputSchema: { type: "object", properties: { query: { type: "string" } }, required: ["query"] },
      level: 1, category: "browser", readOnly: true,
      handler: (args) => bridge.command("search_page", { query: String(args.query) }),
    },
    {
      name: "browser_status",
      description: "Status of the browser extension bridge: connected clients and their info.",
      inputSchema: { type: "object", properties: {} },
      level: 1, category: "browser", readOnly: true,
      handler: () => bridge.status(),
    },
  ];
  for (const t of tools) reg.register(t);
}
