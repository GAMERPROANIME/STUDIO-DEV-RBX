/* Node harness: runs the REAL extension provider + agent loop against a minimal DOM stub.
 *
 *   node tests/harness_provider_loop.mjs <site-adapters.js> <agent-loop.js>
 *
 * Prints one JSON object. Nothing here simulates Roblox: it proves the browser side
 * (detect page, type + send, wait for reply, execute via the local API, send results back).
 */
import fs from 'node:fs';
import vm from 'node:vm';

const adaptersSrc = fs.readFileSync(process.argv[2], 'utf8');
const loopSrc = fs.readFileSync(process.argv[3], 'utf8');

function el(props = {}) {
  const node = {
    id: '',
    tagName: 'DIV',
    innerText: '',
    textContent: '',
    value: undefined,
    disabled: false,
    offsetParent: {},
    children: [],
    clicked: 0,
    listeners: {},
    getAttribute(name) {
      return (props.attrs || {})[name] || null;
    },
    closest() {
      return null;
    },
    querySelectorAll() {
      return [];
    },
    getBoundingClientRect() {
      return { width: 120, height: 24, right: 10, bottom: 10 };
    },
    focus() {
      this.focused = true;
    },
    dispatchEvent(event) {
      this.lastEvent = event;
      (this.listeners[event.type] || []).forEach((fn) => fn(event));
      return true;
    },
    addEventListener(type, fn) {
      (this.listeners[type] = this.listeners[type] || []).push(fn);
    },
    click() {
      this.clicked += 1;
    },
    ...props,
  };
  return node;
}

function makeSandbox(queryMap) {
  const sandbox = {
    location: { hostname: 'chat.deepseek.com', href: 'https://chat.deepseek.com/a/chat/1',
                pathname: '/a/chat/1' },
    document: {
      title: 'chat',
      body: el(),
      querySelectorAll(selector) {
        return queryMap[selector] || [];
      },
      querySelector() {
        return null;
      },
    },
    window: { getSelection: () => ({ toString: () => '' }) },
    getComputedStyle: () => ({ display: 'block', visibility: 'visible' }),
    Event: class Event {
      constructor(type) {
        this.type = type;
      }
    },
    InputEvent: class InputEvent {
      constructor(type, init) {
        this.type = type;
        Object.assign(this, init || {});
      }
    },
    KeyboardEvent: class KeyboardEvent {
      constructor(type, init) {
        this.type = type;
        Object.assign(this, init || {});
      }
    },
    NodeFilter: { SHOW_ELEMENT: 1 },
    setTimeout,
    clearTimeout,
    setInterval: () => 0,
    fetch: async () => ({ ok: false, status: 500, text: async () => '{}' }),
    console,
  };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  return sandbox;
}

// ---------------------------------------------------------------- 1. provider: typing + send
const textarea = el({ tagName: 'TEXTAREA', id: 'chat-input', value: '' });
const sendButton = el({ attrs: { 'aria-label': 'Send message' }, disabled: false });
sendButton.tagName = 'DIV';
const queryMap = {
  'textarea#chat-input': [textarea],
  'div[role="button"][aria-label*="Send" i]': [sendButton],
  '.ds-markdown': [el({ innerText: 'Réponse précédente du modèle, déjà affichée.' })],
};
const providerSandbox = makeSandbox(queryMap);
vm.runInContext(adaptersSrc, providerSandbox);
const provider = providerSandbox.__omniBridgeProvider;

const statusBefore = provider.getProviderStatus();
const sendResult = await provider.sendMessage('Bonjour OMNIBRIDGE');
const providerOut = {
  detected: provider.detectProvider(),
  status: statusBefore,
  send: sendResult,
  composerValue: textarea.value,
  inputDispatched: textarea.lastEvent ? textarea.lastEvent.type : '',
  sendButtonClicks: sendButton.clicked,
  latestReply: provider.getLatestAssistantResponse(),
  unknownSite: (() => {
    const other = makeSandbox({});
    other.location.hostname = 'example.com';
    vm.runInContext(adaptersSrc, other);
    return other.__omniBridgeProvider.detectProvider().known;
  })(),
};

// ---------------------------------------------------------------- 2. loop: full auto cycle
const sandbox = makeSandbox({});
vm.runInContext(adaptersSrc, sandbox);
vm.runInContext(loopSrc, sandbox);

const sent = [];
const replies = ['', 'Je vais créer la part.\n```json\n{"calls":[{"tool":"roblox_create_objects","args":{"name":"SpawnPlatform"}}]}\n```',
                 'C\'est fait : la part SpawnPlatform existe dans Workspace.'];
const fakeProvider = {
  detectProvider: () => ({ id: 'deepseek', label: 'DeepSeek', known: true }),
  findComposer: () => ({}),
  getLatestAssistantResponse: () => replies[Math.min(sent.length, replies.length - 1)],
  isGenerating: () => false,
  sendMessage: async (text) => {
    sent.push(text);
    return { sent: true, via: 'bouton', cleared: true };
  },
  getProviderStatus: () => ({ provider: 'deepseek', label: 'DeepSeek', known: true,
                              composer: true, sendButton: true, generating: false }),
};
sandbox.__omniBridgeProvider = fakeProvider;

let runCalls = 0;
const requests = [];
sandbox.fetch = async (url, options = {}) => {
  requests.push({ url, hasAuth: Boolean(options.headers && options.headers.Authorization) });
  let payload;
  if (url.includes('/api/health')) payload = { ok: true, toolCount: 77, permissionLevel: 3 };
  else if (url.includes('/api/webai/prompt')) {
    payload = { prompt: 'PROTOCOLE OMNIBRIDGE', chars: 19, tools: ['roblox_create_objects'] };
  } else if (url.includes('/api/webai/run')) {
    runCalls += 1;
    payload = runCalls === 1
      ? { ok: true, executed: 1, failed: 0, details: [{ tool: 'roblox_create_objects', ok: true }],
          block: '### OMNIBRIDGE RESULTS\n#### 1. roblox_create_objects — OK' }
      : { ok: true, executed: 0, failed: 0, details: [], block: '', error: 'No tool call found' };
  } else {
    payload = { ok: false };
  }
  return { ok: true, status: 200, text: async () => JSON.stringify(payload) };
};

const loop = sandbox.__omniBridgeLoop;
loop.timings = { replyTimeoutMs: 4000, stableMs: 40, pollMs: 15 };
const events = [];
const outcome = await loop.start({
  instruction: 'Crée une part rouge nommée SpawnPlatform',
  token: 'test-token',
  server: 'http://127.0.0.1:8765',
  maxCycles: 4,
  onEvent: (event) => events.push(event.type),
});

console.log(JSON.stringify({
  provider: providerOut,
  loop: {
    outcome,
    messagesSent: sent.length,
    firstMessageStartsWithPrompt: sent[0] ? sent[0].startsWith('PROTOCOLE OMNIBRIDGE') : false,
    firstMessageHasInstruction: sent[0] ? sent[0].includes('Crée une part rouge') : false,
    secondMessageIsResults: sent[1] ? sent[1].startsWith('### OMNIBRIDGE RESULTS') : false,
    runCalls,
    events,
    authOnRequests: requests.every((r) => r.hasAuth),
    running: loop.running,
    executed: loop.status().executed,
  },
}, null, 2));
