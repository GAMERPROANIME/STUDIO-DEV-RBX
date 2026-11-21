/* OMNIBRIDGE — floating panel for AI chat sites without MCP.
 *
 * ChatGPT · DeepSeek · Gemini · Copilot · Grok: a small in-page panel that
 *   1. copies the OMNIBRIDGE prompt (from the local core),
 *   2. reads the last assistant reply (DOM, only when you click),
 *   3. executes that reply's JSON tool calls through the core,
 *   4. copies the real results so you can paste them back in the chat.
 *
 * Deliberate limits: it never types into the chat box, never sends a message,
 * never reads cookies or session tokens, and never runs without a user click.
 */
'use strict';

if (!globalThis.__omniBridgePanelLoaded) {
  globalThis.__omniBridgePanelLoaded = true;

  const DRAG_KEY = 'omnibridge_panel_pos';
  let panelHost = null;

  function adapters() {
    return globalThis.__omniBridgeAdapters || null;
  }

  async function settings() {
    const stored = await chrome.storage.local.get(['server', 'token', 'autoOpen']);
    return {
      server: (stored.server || 'http://127.0.0.1:8765').replace(/\/$/, ''),
      token: stored.token || '',
      autoOpen: stored.autoOpen !== false,
    };
  }

  async function api(path, options = {}) {
    const { server, token } = await settings();
    const headers = { 'Content-Type': 'application/json' };
    if (token) headers.Authorization = `Bearer ${token}`;
    const res = await fetch(server + path, { ...options, headers });
    const text = await res.text();
    let data;
    try { data = text ? JSON.parse(text) : {}; } catch { data = { raw: text }; }
    if (!res.ok) {
      const detail = data.detail || data;
      throw new Error(typeof detail === 'object' ? (detail.message || JSON.stringify(detail)) : String(detail));
    }
    return data;
  }

  async function copy(text) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      const area = document.createElement('textarea');
      area.value = text;
      area.style.position = 'fixed';
      area.style.opacity = '0';
      document.body.appendChild(area);
      area.select();
      const ok = document.execCommand('copy');
      area.remove();
      return ok;
    }
  }

  function buildPanel() {
    const host = document.createElement('div');
    host.id = 'omnibridge-panel';
    host.style.cssText = 'all: initial; position: fixed; z-index: 2147483647; right: 18px; bottom: 18px;';
    const root = host.attachShadow({ mode: 'open' });
    root.innerHTML = `
      <style>
        :host { all: initial; }
        .wrap { font-family: system-ui, -apple-system, "Segoe UI", sans-serif; font-size: 12px;
                width: 320px; color: #e6edf7; background: #0b0f17ee; border: 1px solid #22304d;
                border-radius: 12px; box-shadow: 0 12px 40px #0009; overflow: hidden;
                backdrop-filter: blur(8px); }
        .head { display: flex; align-items: center; gap: 6px; padding: 8px 10px; cursor: move;
                background: linear-gradient(180deg, #14203a, #0e1626); border-bottom: 1px solid #1e2b40; }
        .logo { font-weight: 700; letter-spacing: .3px; }
        .logo b { color: #22d3ee; }
        .grow { flex: 1; }
        .dot { width: 7px; height: 7px; border-radius: 50%; background: #64748b; }
        .dot.ok { background: #34d399; } .dot.err { background: #f87171; }
        button { font: inherit; cursor: pointer; border-radius: 7px; border: 1px solid #22304d;
                 background: #17233a; color: #dbe7f8; padding: 5px 8px; }
        button.primary { background: #4f8cff; border-color: #4f8cff; color: #fff; font-weight: 600; }
        button:hover { filter: brightness(1.12); }
        button:disabled { opacity: .45; cursor: default; }
        .body { padding: 9px 10px 10px; display: flex; flex-direction: column; gap: 6px; }
        .row { display: flex; gap: 6px; }
        .row > button { flex: 1; }
        label { font-size: 10px; text-transform: uppercase; letter-spacing: .6px; color: #8b9bb4; }
        textarea { width: 100%; box-sizing: border-box; background: #0a111c; color: #cbd8ea;
                   border: 1px solid #1e2b40; border-radius: 7px; padding: 6px; resize: vertical;
                   font-family: ui-monospace, monospace; font-size: 10.5px; line-height: 1.45; }
        .status { font-size: 10.5px; color: #8b9bb4; min-height: 13px; }
        .status.err { color: #f87171; }
        .status.ok { color: #34d399; }
        .collapsed .body { display: none; }
      </style>
      <div class="wrap">
        <div class="head">
          <span class="dot"></span>
          <span class="logo">◈ OMNIBRIDGE <b>AI</b></span>
          <span class="grow"></span>
          <button data-act="toggle" title="Réduire / déplier">–</button>
        </div>
        <div class="body">
          <div class="row">
            <button data-act="prompt" class="primary">Prompt</button>
            <button data-act="read">Lire la réponse</button>
          </div>
          <label>Réponse du modèle / résultats</label>
          <textarea data-el="text" rows="5" placeholder="Cliquez « Lire la réponse », ou collez ici le JSON du modèle."></textarea>
          <div class="row">
            <button data-act="run" class="primary">Exécuter</button>
            <button data-act="copyResult">Copier</button>
          </div>
          <div class="status" data-el="status">Prêt · cliquez sur Prompt pour commencer.</div>
        </div>
      </div>`;
    document.documentElement.appendChild(host);
    return { host, root };
  }

  function wire(root, host) {
    const text = root.querySelector('[data-el="text"]');
    const statusEl = root.querySelector('[data-el="status"]');
    const dot = root.querySelector('.dot');
    const toggle = root.querySelector('[data-act="toggle"]');
    let lastResult = '';

    const setStatus = (message, kind = '') => {
      statusEl.textContent = message;
      statusEl.className = 'status ' + kind;
      dot.className = 'dot' + (kind === 'ok' ? ' ok' : kind === 'err' ? ' err' : '');
    };

    root.querySelector('[data-act="prompt"]').onclick = async () => {
      setStatus('Génération du prompt…');
      try {
        const res = await api('/api/webai/prompt?budgetChars=6000');
        const ok = await copy(res.prompt);
        text.value = res.prompt;
        setStatus(ok ? `Prompt copié (${res.chars} car., ${res.tools.length} outils) — collez-le dans la conversation.`
                     : 'Prompt généré mais presse-papier refusé.', ok ? 'ok' : 'err');
      } catch (e) {
        setStatus('Core injoignable : ' + e.message, 'err');
      }
    };

    root.querySelector('[data-act="read"]').onclick = async () => {
      const a = adapters();
      if (!a) { setStatus('Adapters indisponibles.', 'err'); return; }
      const found = a.lastAssistantMessage();
      const value = found.selectedText || found.text;
      if (!value) { setStatus('Aucune réponse détectée — sélectionnez le texte à la main.', 'err'); return; }
      text.value = value;
      setStatus(`Réponse lue (${found.label || found.site}${found.selector ? ' · ' + found.selector : ''}, ${value.length} car.)`, 'ok');
    };

    root.querySelector('[data-act="run"]').onclick = async () => {
      const reply = text.value.trim();
      if (!reply) { setStatus('Rien à exécuter.', 'err'); return; }
      setStatus('Exécution des appels…');
      try {
        const res = await api('/api/webai/run', { method: 'POST', body: JSON.stringify({ reply }) });
        if (res.block) {
          lastResult = res.block;
          text.value = res.block;
          await copy(res.block);
          setStatus(`${res.executed} appel(s) exécuté(s)` + (res.failed ? `, ${res.failed} échec(s)` : '') +
                    ' — résultats copiés, recollez-les dans la conversation.', res.failed ? 'err' : 'ok');
        } else {
          setStatus(res.error || 'Aucun appel trouvé dans le texte.', 'err');
        }
      } catch (e) {
        setStatus('Erreur : ' + e.message, 'err');
      }
    };

    root.querySelector('[data-act="copyResult"]').onclick = async () => {
      const value = lastResult || text.value;
      if (!value) { setStatus('Rien à copier.', 'err'); return; }
      const ok = await copy(value);
      setStatus(ok ? 'Copié dans le presse-papier.' : 'Presse-papier refusé.', ok ? 'ok' : 'err');
    };

    const wrap = root.querySelector('.wrap');
    toggle.onclick = () => {
      wrap.classList.toggle('collapsed');
      toggle.textContent = wrap.classList.contains('collapsed') ? '+' : '–';
    };

    // Draggable header, position persisted.
    const head = root.querySelector('.head');
    let dragging = false;
    let startX = 0;
    let startY = 0;
    let startRight = 0;
    let startBottom = 0;
    head.addEventListener('mousedown', (e) => {
      if (e.target.tagName === 'BUTTON') return;
      dragging = true;
      startX = e.clientX;
      startY = e.clientY;
      const rect = host.getBoundingClientRect();
      startRight = window.innerWidth - rect.right;
      startBottom = window.innerHeight - rect.bottom;
      e.preventDefault();
    });
    window.addEventListener('mousemove', (e) => {
      if (!dragging) return;
      host.style.right = Math.max(4, startRight - (e.clientX - startX)) + 'px';
      host.style.bottom = Math.max(4, startBottom - (e.clientY - startY)) + 'px';
    });
    window.addEventListener('mouseup', () => {
      if (!dragging) return;
      dragging = false;
      chrome.storage.local.set({ [DRAG_KEY]: { right: host.style.right, bottom: host.style.bottom } });
    });

    chrome.storage.local.get([DRAG_KEY]).then((stored) => {
      const pos = stored[DRAG_KEY];
      if (pos && pos.right) host.style.right = pos.right;
      if (pos && pos.bottom) host.style.bottom = pos.bottom;
    });

    // Show the core status once, read-only.
    api('/api/health')
      .then((h) => setStatus(`Core connecté · ${h.toolCount} outils · niveau ${h.permissionLevel}.`, 'ok'))
      .catch((e) => setStatus('Core non joignable (' + e.message + ') — lancez `omnibridge --transport http`.', 'err'));
  }

  async function start() {
    const { autoOpen } = await settings();
    if (!autoOpen || panelHost) return;
    if (!adapters() || !adapters().site()) return;
    panelHost = buildPanel();
    wire(panelHost.root, panelHost.host);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start, { once: true });
  } else {
    start();
  }

  chrome.storage.onChanged.addListener((changes) => {
    if (changes.autoOpen && changes.autoOpen.newValue === false && panelHost) {
      panelHost.host.remove();
      panelHost = null;
    } else if (changes.autoOpen && changes.autoOpen.newValue !== false) {
      start();
    }
  });
}
