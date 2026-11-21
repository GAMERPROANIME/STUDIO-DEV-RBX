/**
 * Curated documentation sources. Only official docs are fetched by default;
 * every fetched document is stored with source, version (when known),
 * fetch date and reliability so the agent can cite and date facts.
 */
export interface DocSource {
  id: string;
  title: string;
  url: string;
  reliability: "official" | "community";
  version?: string;
}

export const DOC_SOURCES: DocSource[] = [
  { id: "mcp-spec", title: "Model Context Protocol Specification", url: "https://modelcontextprotocol.io/specification/2025-11-25", reliability: "official", version: "2025-11-25" },
  { id: "mcp-typescript-sdk", title: "MCP TypeScript SDK", url: "https://github.com/modelcontextprotocol/typescript-sdk", reliability: "official" },
  { id: "roblox-creator-docs", title: "Roblox Creator Documentation", url: "https://create.roblox.com/docs", reliability: "official" },
  { id: "roblox-studio-mcp", title: "Roblox Studio MCP Server docs", url: "https://create.roblox.com/docs/studio/mcp", reliability: "official" },
  { id: "luau-docs", title: "Luau Language Documentation", url: "https://luau.org/syntax", reliability: "official" },
  { id: "roblox-open-cloud", title: "Roblox Open Cloud API", url: "https://create.roblox.com/docs/open-cloud", reliability: "official" },
  { id: "rojo-docs", title: "Rojo Documentation", url: "https://rojo.space/docs/", reliability: "community" },
];

export async function fetchText(url: string, timeoutMs = 20_000, maxBytes = 1_500_000): Promise<string> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(url, {
      signal: ctrl.signal,
      headers: { "User-Agent": "OMNIBRIDGE-AI/1.0 (+local knowledge indexer)", Accept: "text/html,text/plain,*/*" },
      redirect: "follow",
    });
    if (!res.ok) throw new Error(`HTTP ${res.status} fetching ${url}`);
    const buf = Buffer.from(await res.arrayBuffer());
    return buf.subarray(0, maxBytes).toString("utf8");
  } finally {
    clearTimeout(timer);
  }
}

/** Minimal HTML→text extraction (headings kept as markers). No external deps. */
export function htmlToText(html: string): string {
  return html
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<h([1-6])[^>]*>([\s\S]*?)<\/h\1>/gi, "\n\n## $2\n")
    .replace(/<li[^>]*>/gi, "\n- ")
    .replace(/<p[^>]*>/gi, "\n\n")
    .replace(/<br[^>]*>/gi, "\n")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/g, " ").replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">")
    .replace(/[ \t]+/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}
