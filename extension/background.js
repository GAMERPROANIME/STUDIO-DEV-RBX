/* OMNIBRIDGE extension — background service worker (Chromium MV3 / Firefox MV3).
 *
 * Transport 1 (primary): HTTP long-poll against the Python core (/bridge/*).
 * Transport 2 (optional): Native Messaging to the Python Desktop Bridge host
 *   (com.omnibridge.host) for popup-initiated actions.
 *
 * The extension EXECUTES commands requested by the core's browser_* tools.
 * It never decides what to send on its own and never reads cookies, passwords
 * or form values.
 */
'use strict';

const HOST_NAME = 'com.omnibridge.host';
const DEFAULT_SERVER = 'http://127.0.0.1:8765';

const state = {
  clientId: null,
  connected: false,
  polling: false,
  armedUntil: 0,
  mode: 'manual',
  lastError: '',
  lastCommand: null,
  transport: 'http',
};

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function settings() {
  const s = await chrome.storage.local.get(['server', 'token', 'mode', 'armedUntil', 'clientId']);
  return {
    server: (s.server || DEFAULT_SERVER).replace(/\/$/, ''),
    token: s.token || '',
    mode: s.mode || 'manual',
    armedUntil: s.armedUntil || 0,
    clientId: s.clientId || null,
  };
}

async function authHeaders() {
  const { token } = await settings();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function apiFetch(path, options = {}) {
  const { server } = await settings();
  const headers = { ...(options.headers || {}), ...(await authHeaders()) };
  const res = await fetch(server + path, { ...options, headers });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`HTTP ${res.status}: ${body.slice(0, 300)}`);
  }
  return res.json();
}

/* ---------- authorisation window (manual mode) ---------- */

async function authorize(minutes = 10) {
  const armedUntil = Date.now() + minutes * 60 * 1000;
  await chrome.storage.local.set({ armedUntil });
  state.armedUntil = armedUntil;
  return armedUntil;
}

async function isAuthorized() {
  const { mode, armedUntil } = await settings();
  state.mode = mode;
  state.armedUntil = armedUntil;
  if (mode === 'manual') return Date.now() < armedUntil;
  return true;
}

/* ---------- registration + long poll ---------- */

async function register() {
  const { mode } = await settings();
  if (!state.clientId) {
    state.clientId = (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random());
    await chrome.storage.local.set({ clientId: state.clientId });
  }
  const data = await apiFetch('/bridge/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      clientId: state.clientId,
      info: { mode, userAgent: navigator.userAgent, transport: 'http' },
    }),
  });
  state.connected = Boolean(data.ok);
  state.lastError = '';
  return data;
}

async function submitResult(requestId, ok, data) {
  try {
    await apiFetch('/bridge/result', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ requestId, ok, data }),
    });
  } catch (e) {
    state.lastError = 'result: ' + String(e);
  }
}

async function pollLoop() {
  if (state.polling) return;
  state.polling = true;
  while (state.polling) {
    try {
      if (!state.connected) {
        await register();
        if (!state.connected) await sleep(3000);
        continue;
      }
      const payload = await apiFetch('/bridge/poll', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ clientId: state.clientId, timeoutMs: 25000 }),
      });
      const command = payload.command;
      if (!command) continue;
      state.lastCommand = { type: command.type, at: Date.now() };
      if (!(await isAuthorized())) {
        await submitResult(command.requestId, false,
          `Mode ${state.mode} non autorisé : cliquez sur « Autoriser » dans le popup.`);
        continue;
      }
      const result = await execute(command);
      await submitResult(command.requestId, result.ok, result.data);
    } catch (e) {
      state.connected = false;
      state.lastError = String(e);
      await sleep(3000);
    }
  }
}

/* ---------- command execution ---------- */

const RESEARCH_ALLOWED = ['get_active_tab', 'get_page_content', 'get_selected_text', 'get_links', 'search_page', 'get_page_info'];
const CONTEXTUAL_ALLOWED = RESEARCH_ALLOWED.concat(['capture_page']);

function modeAllows(type, mode) {
  if (mode === 'research') return RESEARCH_ALLOWED.includes(type);
  if (mode === 'contextual') return CONTEXTUAL_ALLOWED.includes(type);
  return true; // manual (after authorisation) and developer
}

async function activeTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab) throw new Error('No active tab');
  return tab;
}

async function sendToTab(tabId, msg) {
  try {
    return await chrome.tabs.sendMessage(tabId, msg);
  } catch (e) {
    // Content script not injected (e.g. chrome:// or a page loaded before install).
    await chrome.scripting.executeScript({ target: { tabId }, files: ['content.js'] });
    return chrome.tabs.sendMessage(tabId, msg);
  }
}

async function execute(command) {
  try {
    const mode = (await settings()).mode;
    if (!modeAllows(command.type, mode)) {
      return { ok: false, data: `Commande « ${command.type} » refusée en mode ${mode}.` };
    }
    const tab = await activeTab();
    const args = command.args || {};
    switch (command.type) {
      case 'get_active_tab':
        return { ok: true, data: { id: tab.id, url: tab.url, title: tab.title, active: true } };
      case 'get_page_content':
        return { ok: true, data: await sendToTab(tab.id, { type: 'get_page_content', maxChars: args.maxChars || 30000 }) };
      case 'get_selected_text':
        return { ok: true, data: await sendToTab(tab.id, { type: 'get_selected_text' }) };
      case 'get_links':
        return { ok: true, data: await sendToTab(tab.id, { type: 'get_links', limit: args.limit || 100 }) };
      case 'search_page':
        return { ok: true, data: await sendToTab(tab.id, { type: 'search_page', query: String(args.query || '') }) };
      case 'get_page_info':
        return { ok: true, data: await sendToTab(tab.id, { type: 'get_page_info' }) };
      case 'capture_page': {
        const dataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, { format: 'png' });
        return { ok: true, data: { format: 'png', base64: dataUrl.split(',')[1] || '' } };
      }
      default:
        return { ok: false, data: `Unknown command: ${command.type}` };
    }
  } catch (e) {
    return { ok: false, data: String(e) };
  }
}

/* ---------- optional native messaging (Desktop Bridge, Python host) ---------- */

let nativePort = null;

function ensureNativePort() {
  if (nativePort) return nativePort;
  try {
    nativePort = chrome.runtime.connectNative(HOST_NAME);
    nativePort.onDisconnect.addListener(() => {
      const err = chrome.runtime.lastError;
      if (err) state.lastError = 'native: ' + err.message;
      nativePort = null;
      state.transport = 'http';
    });
  } catch (e) {
    state.lastError = 'native: ' + String(e);
    state.transport = 'http';
    nativePort = null;
  }
  return nativePort;
}

function nativeRequest(command, payload) {
  return new Promise((resolve) => {
    const port = ensureNativePort();
    if (!port) return resolve({ ok: false, error: 'Native host unavailable' });
    const id = Date.now() + Math.random();
    const onMessage = (msg) => {
      if (msg && msg.id === id) {
        port.onMessage.removeListener(onMessage);
        state.transport = 'native';
        resolve(msg);
      }
    };
    port.onMessage.addListener(onMessage);
    port.postMessage({ id, command, payload });
    setTimeout(() => {
      port.onMessage.removeListener(onMessage);
      resolve({ ok: false, error: 'Native host timeout' });
    }, 30000);
  });
}

/* ---------- messaging with the popup ---------- */

async function statusSnapshot() {
  const s = await settings();
  return {
    connected: state.connected,
    clientId: state.clientId,
    mode: s.mode,
    server: s.server,
    hasToken: Boolean(s.token),
    authorized: s.mode === 'manual' ? Date.now() < s.armedUntil : true,
    armedUntil: s.armedUntil,
    lastError: state.lastError,
    lastCommand: state.lastCommand,
    transport: state.transport,
  };
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  (async () => {
    try {
      switch (msg.type) {
        case 'status':
          sendResponse(await statusSnapshot());
          break;
        case 'connect':
          await chrome.storage.local.set({ server: msg.server || DEFAULT_SERVER, token: msg.token || '', mode: msg.mode || 'manual' });
          state.connected = false;
          await register();
          pollLoop();
          sendResponse({ ok: true, status: await statusSnapshot() });
          break;
        case 'authorize':
          await authorize(msg.minutes || 10);
          sendResponse({ ok: true, status: await statusSnapshot() });
          break;
        case 'disconnect':
          state.connected = false;
          state.polling = false;
          sendResponse({ ok: true, status: await statusSnapshot() });
          break;
        case 'native_status': {
          const res = await nativeRequest('status', {});
          sendResponse({ ok: res.ok, result: res.result, error: res.error });
          break;
        }
        case 'core_tools': {
          const res = await nativeRequest('tools', {});
          sendResponse({ ok: res.ok, result: res.result, error: res.error });
          break;
        }
        case 'native_call': {
          const res = await nativeRequest('call', { name: msg.name, args: msg.args || {}, confirm: Boolean(msg.confirm) });
          sendResponse({ ok: res.ok, result: res.result, error: res.error });
          break;
        }
        default:
          sendResponse({ ok: false, error: 'Unknown message: ' + msg.type });
      }
    } catch (e) {
      sendResponse({ ok: false, error: String(e) });
    }
  })();
  return true;
});

/* Keep the service worker alive and resume polling after suspension. */
chrome.alarms.create('omnibridge-keepalive', { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener((a) => {
  if (a.name === 'omnibridge-keepalive') pollLoop();
});
chrome.runtime.onStartup.addListener(() => pollLoop());
chrome.runtime.onInstalled.addListener(async () => {
  const s = await settings();
  await chrome.storage.local.set({ server: s.server || DEFAULT_SERVER, mode: s.mode || 'manual' });
  pollLoop();
});

pollLoop();
