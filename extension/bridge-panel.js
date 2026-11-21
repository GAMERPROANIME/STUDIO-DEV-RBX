/* OMNIBRIDGE — in-page panel for AI chat sites (DeepSeek, ChatGPT, Gemini, Copilot, Grok).
 *
 * Two modes, one panel:
 *
 *   AUTOMATIQUE (par défaut)
 *     [Connecter]  → vérifie la page, le serveur local et Roblox Studio (3 voyants)
 *     [Démarrer]   → agent-loop.js écrit le prompt dans le chat, attend la réponse, exécute les
 *                    appels d'outils dans Studio, renvoie les résultats, et recommence.
 *     [Arrêter]    → arrêt immédiat, à tout moment.
 *
 *   MANUEL (replié)
 *     Prompt · Lire la réponse · Exécuter · Copier — les mêmes actions, clic par clic.
 *
 * Nothing runs before you click: no auto-start, no auto-send at load. It never reads cookies,
 * passwords or session tokens, and only talks to 127.0.0.1/localhost with the user's token.
 */
'use strict';

if (!globalThis.__omniBridgePanelLoaded) {
  globalThis.__omniBridgePanelLoaded = true;

  const DRAG_KEY = 'omnibridge_panel_pos';
  let panelHost = null;

  function providerApi() {
    return globalThis.__omniBridgeProvider || globalThis.__omniBridgeAdapters || null;
  }

  function loopApi() {
    return globalThis.__omniBridgeLoop || null;
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
    try {
      data = text ? JSON.parse(text) : {};
    } catch {
      data = { raw: text };
    }
    if (!res.ok) {
      const detail = data.detail || data;
      throw new Error(typeof detail === 'object'
        ? detail.message || JSON.stringify(detail)
        : String(detail));
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
                width: 330px; color: #e6edf7; background: #0b0f17ee; border: 1px solid #22304d;
                border-radius: 12px; box-shadow: 0 12px 40px #0009; overflow: hidden;
                backdrop-filter: blur(8px); }
        .head { display: flex; align-items: center; gap: 6px; padding: 8px 10px; cursor: move;
                background: linear-gradient(180deg, #14203a, #0e1626); border-bottom: 1px solid #1e2b40; }
        .logo { font-weight: 700; letter-spacing: .3px; }
        .logo b { color: #22d3ee; }
        .grow { flex: 1; }
        .tag { font-size: 10px; color: #93c5fd; border: 1px solid #1e3a5f; border-radius: 999px;
               padding: 1px 7px; }
        .dot { width: 7px; height: 7px; border-radius: 50%; background: #64748b; flex: 0 0 auto; }
        .dot.ok { background: #34d399; } .dot.err { background: #f87171; } .dot.warn { background: #fbbf24; }
        button { font: inherit; cursor: pointer; border-radius: 7px; border: 1px solid #22304d;
                 background: #17233a; color: #dbe7f8; padding: 5px 8px; }
        button.primary { background: #4f8cff; border-color: #4f8cff; color: #fff; font-weight: 600; }
        button.danger { background: #7f1d1d; border-color: #b91c1c; color: #fee2e2; }
        button:hover { filter: brightness(1.12); }
        button:disabled { opacity: .45; cursor: default; }
        .body { padding: 9px 10px 10px; display: flex; flex-direction: column; gap: 7px; }
        .row { display: flex; gap: 6px; }
        .row > button { flex: 1; }
        .checks { display: flex; flex-direction: column; gap: 3px; }
        .check { display: flex; align-items: center; gap: 6px; font-size: 11px; color: #b6c4d8; }
        .check .val { color: #8b9bb4; margin-left: auto; font-size: 10px; }
        label { font-size: 10px; text-transform: uppercase; letter-spacing: .6px; color: #8b9bb4; }
        textarea { width: 100%; box-sizing: border-box; background: #0a111c; color: #cbd8ea;
                   border: 1px solid #1e2b40; border-radius: 7px; padding: 6px; resize: vertical;
                   font-family: ui-monospace, monospace; font-size: 10.5px; line-height: 1.45; }
        .status { font-size: 10.5px; color: #8b9bb4; min-height: 13px; }
        .status.err { color: #f87171; } .status.ok { color: #34d399; } .status.warn { color: #fbbf24; }
        .log { font-family: ui-monospace, monospace; font-size: 10px; line-height: 1.45;
               background: #080d15; border: 1px solid #16202f; border-radius: 7px; padding: 5px;
               max-height: 82px; overflow: auto; color: #93a4bb; white-space: pre-wrap; }
        details { border-top: 1px solid #16202f; padding-top: 6px; }
        summary { cursor: pointer; font-size: 10px; text-transform: uppercase; letter-spacing: .6px;
                  color: #8b9bb4; }
        .collapsed .body { display: none; }
      </style>
      <div class="wrap">
        <div class="head">
          <span class="dot" data-el="headDot"></span>
          <span class="logo">◈ OMNIBRIDGE <b>AI</b></span>
          <span class="grow"></span>
          <span class="tag" data-el="providerTag">…</span>
          <button data-act="toggle" title="Réduire / déplier">–</button>
        </div>
        <div class="body">
          <div class="checks">
            <div class="check"><span class="dot" data-el="pageDot"></span> Page IA
              <span class="val" data-el="pageVal">…</span></div>
            <div class="check"><span class="dot" data-el="coreDot"></span> Serveur local
              <span class="val" data-el="coreVal">…</span></div>
            <div class="check"><span class="dot" data-el="studioDot"></span> Roblox Studio
              <span class="val" data-el="studioVal">…</span></div>
          </div>
          <button data-act="connect" class="primary">Connecter</button>

          <label for="omnibridge-instruction">Ce que je veux faire</label>
          <textarea data-el="instruction" id="omnibridge-instruction" rows="2"
            placeholder="Ex : crée une part rouge de 4×1×4 au-dessus de la base, nommée SpawnPlatform."></textarea>
          <div class="row">
            <button data-act="start" class="primary" disabled>Démarrer la boucle</button>
            <button data-act="stop" class="danger" disabled>Arrêter</button>
          </div>
          <div class="status" data-el="status">Clique sur « Connecter » pour vérifier les 3 voyants.</div>
          <div class="log" data-el="log">—</div>

          <details>
            <summary>Mode manuel (4 boutons)</summary>
            <div class="row" style="margin-top:6px">
              <button data-act="prompt">Prompt</button>
              <button data-act="read">Lire la réponse</button>
            </div>
            <label style="margin-top:6px;display:block">Réponse / résultats</label>
            <textarea data-el="text" rows="4"
              placeholder="Clique sur « Lire la réponse », ou colle ici le JSON du modèle."></textarea>
            <div class="row">
              <button data-act="run" class="primary">Exécuter</button>
              <button data-act="copyResult">Copier</button>
            </div>
          </details>
        </div>
      </div>`;
    document.documentElement.appendChild(host);
    return { host, root };
  }

  function wire(root, host) {
    const text = root.querySelector('[data-el="text"]');
    const statusEl = root.querySelector('[data-el="status"]');
    const logEl = root.querySelector('[data-el="log"]');
    const instruction = root.querySelector('[data-el="instruction"]');
    const toggle = root.querySelector('[data-act="toggle"]');
    const startBtn = root.querySelector('[data-act="start"]');
    const stopBtn = root.querySelector('[data-act="stop"]');
    const connectBtn = root.querySelector('[data-act="connect"]');
    const providerTag = root.querySelector('[data-el="providerTag"]');
    const dots = {
      head: root.querySelector('[data-el="headDot"]'),
      page: root.querySelector('[data-el="pageDot"]'),
      core: root.querySelector('[data-el="coreDot"]'),
      studio: root.querySelector('[data-el="studioDot"]'),
    };
    const values = {
      page: root.querySelector('[data-el="pageVal"]'),
      core: root.querySelector('[data-el="coreVal"]'),
      studio: root.querySelector('[data-el="studioVal"]'),
    };
    let lastResult = '';
    let connected = false;
    const logLines = [];

    const setDot = (key, state) => {
      const dot = dots[key];
      if (dot) dot.className = 'dot' + (state ? ' ' + state : '');
    };
    const setStatus = (message, kind = '') => {
      statusEl.textContent = message;
      statusEl.className = 'status ' + kind;
      setDot('head', kind === 'ok' ? 'ok' : kind === 'err' ? 'err' : kind === 'warn' ? 'warn' : '');
    };
    const pushLog = (line) => {
      logLines.push(line);
      while (logLines.length > 60) logLines.shift();
      logEl.textContent = logLines.slice(-8).join('\n');
      logEl.scrollTop = logEl.scrollHeight;
      logEl.scrollTop = logEl.scrollHeight;
    };

    const refreshProvider = () => {
      const provider = providerApi();
      if (!provider) return { known: false, label: 'inconnu' };
      const status = provider.getProviderStatus();
      providerTag.textContent = status.label || status.provider;
      values.page.textContent = status.composer
        ? (status.sendButton ? 'prête' : 'prête (envoi touche Entrée)')
        : 'zone de texte introuvable';
      setDot('page', status.composer ? 'ok' : 'err');
      return status;
    };

    const checkStudio = async () => {
      setDot('studio', 'warn');
      values.studio.textContent = 'vérification…';
      try {
        const info = await api('/api/roblox');
        if (info && info.available) {
          const count = (info.tools || []).length;
          values.studio.textContent = count ? `${count} outils` : 'connecté';
          setDot('studio', 'ok');
          return true;
        }
        const reason = (info && info.error) || 'non connecté';
        values.studio.textContent = /not found|introuvable/i.test(reason)
          ? 'Studio fermé / MCP désactivé' : reason.slice(0, 46);
        setDot('studio', 'err');
        return false;
      } catch (error) {
        values.studio.textContent = 'serveur local requis';
        setDot('studio', 'err');
        return false;
      }
    };

    const connect = async () => {
      connectBtn.disabled = true;
      setStatus('Vérification…');
      const providerStatus = refreshProvider();
      setDot('core', 'warn');
      values.core.textContent = 'vérification…';
      let coreOk = false;
      let toolCount = 0;
      try {
        const health = await api('/api/health');
        coreOk = Boolean(health && health.ok);
        toolCount = health.toolCount || 0;
        values.core.textContent = coreOk ? `${toolCount} outils · niveau ${health.permissionLevel}` : 'réponse inattendue';
        setDot('core', coreOk ? 'ok' : 'err');
      } catch (error) {
        values.core.textContent = 'injoignable';
        setDot('core', 'err');
      }
      const studioOk = coreOk ? await checkStudio() : false;
      connectBtn.disabled = false;

      connected = Boolean(providerStatus && providerStatus.composer && coreOk);
      startBtn.disabled = !connected;
      if (!coreOk) {
        setStatus('Serveur local injoignable : lance DEMARRER-PANNEAU (fenêtre noire).', 'err');
        return false;
      }
      if (!providerStatus || !providerStatus.composer) {
        setStatus('Zone de saisie introuvable : ouvre une conversation puis réessaie.', 'err');
        return false;
      }
      if (!studioOk) {
        setStatus('Serveur OK, mais Studio pas connecté : ouvre Studio et active le serveur MCP.', 'warn');
        return false;
      }
      setStatus(`Tout est connecté (${providerStatus.label} · ${toolCount} outils). Tu peux démarrer.`, 'ok');
      return true;
    };

    const start = async () => {
      const loop = loopApi();
      if (!loop) {
        setStatus('Boucle indisponible (agent-loop.js non chargé).', 'err');
        return;
      }
      startBtn.disabled = true;
      stopBtn.disabled = false;
      setStatus('Démarrage…');
      const { server, token } = await settings();
      const outcome = await loop.start({
        instruction: instruction.value,
        server,
        token,
        maxCycles: 10,
        onEvent: (event) => {
          if (event.type === 'cycle') {
            setStatus(`Cycle ${event.cycle}/${event.max} — l'IA réfléchit…`, 'ok');
            pushLog(`[cycle ${event.cycle}] en attente de la réponse`);
          } else if (event.type === 'reply') {
            pushLog(`[réponse] ${event.chars} caractères`);
          } else if (event.type === 'executed') {
            pushLog(`[exécuté] ${event.executed} outil(s)${event.failed ? `, ${event.failed} échec(s)` : ''}`);
            setStatus(`${event.executed} outil(s) exécuté(s) dans Studio — résultats renvoyés.`, 'ok');
          } else if (event.type === 'log') {
            pushLog(event.text);
            if (event.level === 'warn') setStatus(event.text, 'warn');
          } else if (event.type === 'error') {
            pushLog(`[erreur] ${event.text}`);
            setStatus(event.text, 'err');
          } else if (event.type === 'done') {
            setStatus('Réponse finale reçue — rien de plus à exécuter.', 'ok');
            pushLog('[fin] réponse finale');
          } else if (event.type === 'stopped') {
            const reason = event.stopReason || 'terminé';
            pushLog(`[arrêt] ${reason}`);
            setStatus(`Boucle arrêtée (${reason}).`, event.stopReason === 'anti_doublon' ? 'warn' : 'ok');
          }
        },
      });
      startBtn.disabled = false;
      stopBtn.disabled = true;
      if (!outcome.ok) {
        const labels = {
          core_injoignable: 'Serveur local injoignable — lance DEMARRER-PANNEAU.',
          site_non_supporte: 'Ce site n\'est pas pris en charge.',
          composer_introuvable: 'Zone de saisie introuvable.',
          envoi_impossible: 'Impossible d\'écrire dans le chat.',
          envoi_refuse: 'Le message n\'est pas parti (vérifie le champ de saisie).',
          deja_en_cours: 'La boucle tourne déjà.',
        };
        setStatus(labels[outcome.code] || `Échec : ${outcome.code || 'inconnu'}`, 'err');
        return;
      }
      pushLog(`[fin] ${outcome.executed} outil(s) exécuté(s) au total`);
    };

    root.querySelector('[data-act="connect"]').onclick = () => {
      connect().catch((error) => setStatus('Erreur : ' + error.message, 'err'));
    };

    startBtn.onclick = () => {
      start().catch((error) => {
        startBtn.disabled = false;
        stopBtn.disabled = true;
        setStatus('Erreur : ' + error.message, 'err');
      });
    };

    stopBtn.onclick = () => {
      const loop = loopApi();
      if (loop && loop.stop('utilisateur')) {
        setStatus('Arrêt demandé…', 'warn');
      }
    };

    root.querySelector('[data-act="prompt"]').onclick = async () => {
      setStatus('Génération du prompt…');
      try {
        const res = await api('/api/webai/prompt?budgetChars=6000');
        const ok = await copy(res.prompt);
        text.value = res.prompt;
        setStatus(ok
          ? `Prompt copié (${res.chars} car., ${res.tools.length} outils) — colle-le dans la conversation.`
          : 'Prompt généré mais presse-papier refusé.', ok ? 'ok' : 'err');
      } catch (error) {
        setStatus('Serveur injoignable : ' + error.message, 'err');
      }
    };

    root.querySelector('[data-act="read"]').onclick = async () => {
      const provider = providerApi();
      if (!provider) { setStatus('Adapters indisponibles.', 'err'); return; }
      const legacy = provider.lastAssistantMessage
        ? provider.lastAssistantMessage()
        : { text: provider.getLatestAssistantResponse(), selectedText: '', label: '' };
      const value = legacy.selectedText || legacy.text;
      if (!value) {
        setStatus('Aucune réponse détectée — sélectionne le texte à la main.', 'err');
        return;
      }
      text.value = value;
      setStatus(`Réponse lue (${value.length} car.).`, 'ok');
    };

    root.querySelector('[data-act="run"]').onclick = async () => {
      const reply = text.value.trim();
      if (!reply) { setStatus('Rien à exécuter.', 'err'); return; }
      setStatus('Exécution des appels…');
      try {
        const res = await api('/api/webai/run', {
          method: 'POST',
          body: JSON.stringify({ reply }),
        });
        if (res.block) {
          lastResult = res.block;
          text.value = res.block;
          await copy(res.block);
          setStatus(`${res.executed} appel(s) exécuté(s)`
            + (res.failed ? `, ${res.failed} échec(s)` : '')
            + ' — résultats copiés, recolle-les dans la conversation.',
          res.failed ? 'err' : 'ok');
        } else {
          setStatus(res.error || 'Aucun appel trouvé dans le texte.', 'err');
        }
      } catch (error) {
        setStatus('Erreur : ' + error.message, 'err');
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
    head.addEventListener('mousedown', (event) => {
      if (event.target.tagName === 'BUTTON') return;
      dragging = true;
      startX = event.clientX;
      startY = event.clientY;
      const rect = host.getBoundingClientRect();
      startRight = window.innerWidth - rect.right;
      startBottom = window.innerHeight - rect.bottom;
      event.preventDefault();
    });
    window.addEventListener('mousemove', (event) => {
      if (!dragging) return;
      host.style.right = Math.max(4, startRight - (event.clientX - startX)) + 'px';
      host.style.bottom = Math.max(4, startBottom - (event.clientY - startY)) + 'px';
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

    // Read-only first look: nothing is typed or sent until the user clicks.
    refreshProvider();
    api('/api/health')
      .then((health) => {
        values.core.textContent = `${health.toolCount} outils · niveau ${health.permissionLevel}`;
        setDot('core', 'ok');
        setStatus(`Serveur prêt (${health.toolCount} outils). Clique sur « Connecter ».`, 'ok');
        return checkStudio();
      })
      .catch((error) => {
        values.core.textContent = 'injoignable';
        setDot('core', 'err');
        setStatus('Serveur non joignable (' + error.message + ') — lance DEMARRER-PANNEAU.', 'err');
      });

    // Keep the page indicator honest when the SPA swaps views.
    const refreshTimer = setInterval(() => {
      const provider = providerApi();
      if (provider && provider.getProviderStatus) refreshProvider();
    }, 4000);
    window.addEventListener('beforeunload', () => clearInterval(refreshTimer));
    void connected;
  }

  async function start() {
    const { autoOpen } = await settings();
    if (!autoOpen || panelHost) return;
    const provider = providerApi();
    if (!provider || !provider.site()) return;
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
