/* OMNIBRIDGE extension — background service worker.
 * Connects to the local OMNIBRIDGE server bridge (long-poll) and executes
 * commands requested by MCP tools (browser_*). Also supports Native Messaging
 * to the Desktop Bridge host when installed (see desktop-bridge/).
 * Modes: manual (popup), contextual (auto active-tab), developer, research.
 */
const SERVER = "http://127.0.0.1:8765";
let clientId = null;
let connected = false;
let mode = "manual"; // manual | contextual | developer | research

async function getToken() {
  const { token } = await chrome.storage.local.get("token");
  return token || "";
}

async function register() {
  const token = await getToken();
  const res = await fetch(`${SERVER}/bridge/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify({ clientId, info: { mode, userAgent: navigator.userAgent } }),
  });
  const data = await res.json();
  clientId = data.clientId;
  connected = true;
  chrome.storage.local.set({ clientId });
  pollLoop();
}

async function pollLoop() {
  while (connected) {
    try {
      const res = await fetch(`${SERVER}/bridge/poll?clientId=${encodeURIComponent(clientId)}`);
      const { command } = await res.json();
      if (command) {
        const result = await execute(command);
        await fetch(`${SERVER}/bridge/result`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ requestId: command.requestId, ok: result.ok, data: result.data }),
        });
      }
    } catch (e) {
      connected = false;
      setTimeout(() => { connected = true; register().catch(() => {}); }, 5000);
    }
  }
}

async function execute(command) {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab) return { ok: false, data: "No active tab" };
    const send = (msg) => chrome.tabs.sendMessage(tab.id, msg);
    switch (command.type) {
      case "get_active_tab":
        return { ok: true, data: { id: tab.id, url: tab.url, title: tab.title } };
      case "get_page_content":
        return { ok: true, data: await send({ type: "get_page_content", maxChars: command.args.maxChars }) };
      case "get_selected_text":
        return { ok: true, data: await send({ type: "get_selected_text" }) };
      case "get_links":
        return { ok: true, data: await send({ type: "get_links", limit: command.args.limit }) };
      case "search_page":
        return { ok: true, data: await send({ type: "search_page", query: command.args.query }) };
      case "capture_page": {
        const dataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, { format: "png" });
        return { ok: true, data: { format: "png", base64: dataUrl.split(",")[1] } };
      }
      default:
        return { ok: false, data: `Unknown command: ${command.type}` };
    }
  } catch (e) {
    return { ok: false, data: String(e) };
  }
}

// Native messaging fallback (Desktop Bridge host) — used when the HTTP bridge
// is unavailable. The host is installed by desktop-bridge/install scripts.
chrome.runtime.onConnect.addListener((port) => {
  if (port.name !== "omnibridge-native") return;
  port.onMessage.addListener(async (msg) => {
    const result = await execute(msg);
    port.postMessage({ requestId: msg.requestId, ...result });
  });
});

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === "set_mode") { mode = msg.mode; sendResponse({ ok: true }); }
  if (msg.type === "status") sendResponse({ connected, clientId, mode });
  if (msg.type === "connect") register().then(() => sendResponse({ ok: true })).catch((e) => sendResponse({ ok: false, error: String(e) }));
  return true;
});

chrome.storage.local.get(["clientId", "mode"]).then((s) => {
  clientId = s.clientId || null;
  if (s.mode) mode = s.mode;
  register().catch(() => {});
});
