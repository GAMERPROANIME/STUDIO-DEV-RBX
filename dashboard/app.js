/* OMNIBRIDGE dashboard — vanilla JS (HTML/CSS + fetch only).
 * Every call hits the Python core HTTP API with the local bearer token.
 */
'use strict';

const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];

let token = localStorage.getItem('omnibridge_token') || '';
let tools = [];
let activeCat = 'all';
let selectedTool = null;

$('#token').value = token;

/* ---------------- API ---------------- */

async function api(path, opts = {}) {
  const headers = { ...(opts.headers || {}) };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (opts.body) headers['Content-Type'] = 'application/json';
  const res = await fetch(path, { ...opts, headers });
  const text = await res.text();
  let data;
  try { data = text ? JSON.parse(text) : {}; } catch { data = { raw: text }; }
  if (!res.ok) {
    const detail = data && data.detail ? data.detail : data;
    const msg = typeof detail === 'object' ? (detail.message || JSON.stringify(detail)) : String(detail);
    throw new Error(`HTTP ${res.status} — ${msg}`);
  }
  return data;
}

const callTool = (name, args = {}, confirm = false) =>
  api('/api/tools/call', { method: 'POST', body: JSON.stringify({ name, args, confirm }) })
    .then((r) => r.result);

$('#saveToken').onclick = () => {
  token = $('#token').value.trim();
  localStorage.setItem('omnibridge_token', token);
  refreshAll();
};

/* ---------------- tabs ---------------- */

$$('#tabs button').forEach((b) => {
  b.onclick = () => {
    $$('#tabs button').forEach((x) => x.classList.remove('active'));
    $$('.tab').forEach((x) => x.classList.remove('active'));
    b.classList.add('active');
    $('#tab-' + b.dataset.tab).classList.add('active');
    if (b.dataset.tab === 'settings') loadSettings();
  };
});

const card = (label, value, cls = '', sub = '') =>
  `<div class="card"><div class="label">${label}</div><div class="value ${cls}">${value}</div>${sub ? `<div class="sub">${sub}</div>` : ''}</div>`;

const pct = (v) => (v ? 'oui' : 'non');

/* ---------------- dashboard ---------------- */

async function loadDashboard() {
  try {
    const h = await api('/api/health');
    $('#footerStatus').textContent = `connecté · ${h.toolCount} outils · L${h.permissionLevel}`;
    $('#footerStatus').className = 'ok';
    $('#healthCards').innerHTML =
      card('Outils MCP', h.toolCount) +
      card('Niveau de permission', 'L' + h.permissionLevel) +
      card('Roblox Studio MCP', h.robloxStudio.available ? 'connecté' : 'non configuré', h.robloxStudio.available ? 'ok' : 'warn') +
      card('Extension navigateur', h.browserBridge.connected ? 'connectée' : 'absente', h.browserBridge.connected ? 'ok' : 'warn') +
      card('Chunks indexés', h.knowledge.chunks) +
      card('Sources indexées', h.knowledge.sources) +
      card('Runtime', 'Python ' + h.runtime.python, '', h.runtime.platform + ' ' + h.runtime.arch) +
      card('Espace de travail', '', '', h.workspace);
    $('#healthDetail').textContent = JSON.stringify(h, null, 2);
  } catch (e) {
    $('#footerStatus').textContent = 'non connecté — ' + e.message;
    $('#footerStatus').className = 'err';
    $('#healthDetail').textContent =
      'Erreur : ' + e.message +
      '\n\n1) Le core tourne-t-il ?  python -m omnibridge --transport http' +
      '\n2) Token correct ?  cat ~/.omnibridge/token.txt';
  }
}

/* ---------------- MCP explorer ---------------- */

async function loadTools() {
  const data = await api('/api/tools');
  tools = data.tools;
  $('#toolCount').textContent = data.count;
  const cats = ['all', ...new Set(tools.map((t) => t.category))];
  $('#catFilters').innerHTML = cats
    .map((c) => `<button data-cat="${c}" class="${c === activeCat ? 'active' : ''}">${c}</button>`)
    .join('');
  $$('#catFilters button').forEach((b) => (b.onclick = () => { activeCat = b.dataset.cat; loadTools(); }));

  const shown = tools.filter((t) => activeCat === 'all' || t.category === activeCat);
  $('#toolList').innerHTML = shown
    .map((t) => `<div class="tool" data-name="${t.name}">
        <div class="name">${t.name}<span class="badge ${t.level === 4 ? 'l4' : t.level === 3 ? 'l3' : ''}">L${t.level}</span></div>
        <div class="meta">${t.category} · ${t.readOnly ? 'lecture seule' : 'écriture'}</div>
        <div class="desc">${escapeHtml(t.description)}</div>
      </div>`)
    .join('');
  $$('#toolList .tool').forEach((el) => (el.onclick = () => selectTool(el.dataset.name)));

  const roblox = tools.filter((t) => t.category === 'roblox');
  $('#robloxTool').innerHTML = roblox.map((t) => `<option value="${t.name}">${t.name}</option>`).join('');
}

function selectTool(name) {
  selectedTool = tools.find((t) => t.name === name);
  if (!selectedTool) return;
  $('#runnerTitle').textContent = `${selectedTool.name} · L${selectedTool.level}`;
  $('#runnerDesc').textContent = selectedTool.description;
  const sample = {};
  const props = selectedTool.inputSchema.properties || {};
  for (const [k, v] of Object.entries(props)) if ('default' in v) sample[k] = v.default;
  $('#runnerArgs').value = JSON.stringify(sample, null, 2);
  $('#runnerResult').textContent = '';
}

$('#runnerRun').onclick = async () => {
  if (!selectedTool) return;
  let args;
  try { args = $('#runnerArgs').value.trim() ? JSON.parse($('#runnerArgs').value) : {}; }
  catch (e) { $('#runnerResult').textContent = 'JSON invalide : ' + e.message; return; }
  $('#runnerResult').textContent = 'Exécution…';
  try {
    const out = await callTool(selectedTool.name, args, $('#runnerConfirm').checked);
    $('#runnerResult').textContent = JSON.stringify(out, null, 2);
    refreshAll();
  } catch (e) {
    $('#runnerResult').textContent = 'Erreur : ' + e.message;
  }
};

/* ---------------- AI connections ---------------- */

async function loadConnections() {
  const info = await api('/api/info');
  const httpUrl = `http://127.0.0.1:${location.port || 8765}/mcp`;
  $('#connectionCards').innerHTML =
    card('Transport MCP', 'Streamable HTTP', 'ok', httpUrl) +
    card('Transport MCP', 'stdio', 'ok', 'python -m omnibridge --stdio') +
    card('Outils exposés', info.toolCount) +
    card('Authentification', 'Bearer token', '', 'header Authorization');
  const httpConfig = {
    mcpServers: {
      omnibridge: {
        type: 'http',
        url: httpUrl,
        headers: { Authorization: 'Bearer <token: ~/.omnibridge/token.txt>' },
      },
    },
  };
  const stdioConfig = {
    mcpServers: {
      omnibridge: {
        command: 'python',
        args: ['-m', 'omnibridge', '--stdio'],
        env: { OMNIBRIDGE_PERMISSION_LEVEL: String(info.permissionLevel) },
      },
    },
  };
  $('#mcpHttpConfig').textContent = JSON.stringify(httpConfig, null, 2);
  $('#mcpStdioConfig').textContent = JSON.stringify(stdioConfig, null, 2);

  try {
    const providers = await api('/api/webai/providers');
    $('#webaiProviders').innerHTML = providers.providers.map((p) =>
      card(p.name, p.needsKey ? 'clé requise' : 'local', p.needsKey ? 'warn' : 'ok',
        `${p.baseUrl} · ${p.defaultModel}${p.apiKeyEnv ? ' · ' + p.apiKeyEnv : ''}`)).join('');
    $('#webaiCommand').textContent =
      '# DeepSeek / OpenAI / Groq (clé dans l\'environnement)\n' +
      'export DEEPSEEK_API_KEY=...\n' +
      'python examples/openai-compatible-agent.py --provider deepseek \\\n' +
      '  "Inspecte ce projet et liste les TODO"\n\n' +
      '# Ollama local (sans clé)\n' +
      'ollama serve && ollama pull qwen2.5-coder:7b\n' +
      'python examples/openai-compatible-agent.py --provider ollama --model qwen2.5-coder:7b "Analyse src/"';
  } catch (e) {
    $('#webaiProviders').innerHTML = card('Ponts IA', 'erreur', 'err', e.message);
  }
}

/* ---------------- universal bridges (chat-only AI + OpenAI-compatible) ---------------- */

let webaiBlock = '';

$('#webaiGen').onclick = async () => {
  const cats = $('#webaiPreset').value;
  $('#webaiPromptInfo').textContent = 'génération…';
  try {
    const res = await api('/api/webai/prompt?budgetChars=7000' + (cats ? `&categories=${encodeURIComponent(cats)}` : ''));
    $('#webaiPrompt').value = res.prompt;
    $('#webaiPromptInfo').textContent = `${res.chars} caractères · ${res.tools.length} outils` +
      (res.toolsOmitted ? ` · ${res.toolsOmitted} omis` : '');
  } catch (e) {
    $('#webaiPromptInfo').textContent = 'erreur : ' + e.message;
  }
};

$('#webaiCopyPrompt').onclick = async () => {
  try {
    await navigator.clipboard.writeText($('#webaiPrompt').value);
    $('#webaiPromptInfo').textContent = 'prompt copié — collez-le dans la conversation';
  } catch {
    $('#webaiPrompt').select();
    document.execCommand('copy');
  }
};

$('#webaiRun').onclick = async () => {
  const reply = $('#webaiReply').value.trim();
  if (!reply) { $('#webaiResult').textContent = 'Collez d\'abord la réponse du modèle.'; return; }
  $('#webaiResult').textContent = 'Exécution des appels…';
  try {
    const res = await api('/api/webai/run', {
      method: 'POST',
      body: JSON.stringify({ reply, confirm: $('#webaiConfirm').checked }),
    });
    webaiBlock = res.block || '';
    $('#webaiResult').textContent = webaiBlock || (res.error || JSON.stringify(res, null, 2));
    refreshAll();
  } catch (e) {
    $('#webaiResult').textContent = 'Erreur : ' + e.message;
  }
};

$('#webaiCopyResult').onclick = async () => {
  if (!webaiBlock) { $('#webaiResult').textContent = 'Rien à copier — exécutez d\'abord des appels.'; return; }
  try { await navigator.clipboard.writeText(webaiBlock); $('#webaiPromptInfo').textContent = 'bloc résultat copié'; }
  catch { $('#webaiResult').select(); document.execCommand('copy'); }
};

$('#webaiCheck').onclick = async () => {
  const url = $('#webaiRemoteUrl').value.trim();
  if (!url) return;
  $('#webaiCheckResult').textContent = 'Vérification…';
  try {
    const res = await api('/api/webai/check', { method: 'POST', body: JSON.stringify({ url }) });
    $('#webaiCheckResult').textContent = JSON.stringify(res, null, 2);
  } catch (e) {
    $('#webaiCheckResult').textContent = 'Erreur : ' + e.message;
  }
};

/* ---------------- extension ---------------- */

async function loadExtension() {
  const s = await api('/api/browser/status');
  $('#extensionCards').innerHTML =
    card('Pont HTTP', s.connected ? 'connecté' : 'aucun client', s.connected ? 'ok' : 'warn') +
    card('Clients', s.clients.length) +
    card('Outils navigateur', tools.filter((t) => t.category === 'browser').length);
}

$('#extRefresh').onclick = async () => {
  try { await loadExtension(); $('#extResult').textContent = 'Statut rafraîchi.'; }
  catch (e) { $('#extResult').textContent = 'Erreur : ' + e.message; }
};

$('#extProbe').onclick = async () => {
  $('#extResult').textContent = 'Requête envoyée à l\'extension…';
  try {
    const out = await callTool('browser_get_active_tab', {});
    $('#extResult').textContent = JSON.stringify(out, null, 2);
  } catch (e) {
    $('#extResult').textContent = 'Erreur : ' + e.message +
      '\n\nL\'extension doit être chargée et connectée (popup → Connecter).';
  }
};

/* ---------------- roblox ---------------- */

async function loadRoblox() {
  const r = await api('/api/roblox');
  $('#robloxCards').innerHTML =
    card('Studio MCP officiel', r.available ? 'disponible' : 'non configuré', r.available ? 'ok' : 'warn',
      r.available ? (r.command || '') : (r.error || '')) +
    card('Outils officiels', (r.tools || []).length) +
    card('Couche Rojo disque', 'active', 'ok', 'roblox_inspect_project / roblox_edit_scripts');
  $('#robloxDetail').textContent = JSON.stringify(r, null, 2);
}

$('#runRobloxTool').onclick = async () => {
  let args = {};
  try { if ($('#robloxArgs').value.trim()) args = JSON.parse($('#robloxArgs').value); }
  catch (e) { $('#robloxResult').textContent = 'JSON invalide : ' + e.message; return; }
  $('#robloxResult').textContent = 'Exécution…';
  try { $('#robloxResult').textContent = JSON.stringify(await callTool($('#robloxTool').value, args), null, 2); }
  catch (e) { $('#robloxResult').textContent = 'Erreur : ' + e.message; }
};

/* ---------------- knowledge ---------------- */

async function loadKnowledge() {
  const s = await api('/api/knowledge/stats');
  $('#knowledgeCards').innerHTML =
    card('Chunks', s.chunks) + card('Sources', s.sources) +
    card('Recherche', 'FTS5 + TF-IDF', 'ok') +
    card('Mémoire', 'SQLite', '', 'personal · project · temp');
}

$('#kbSearch').onclick = async () => {
  const q = $('#kbQuery').value.trim();
  if (!q) return;
  $('#kbResult').textContent = 'Recherche…';
  try {
    const res = await api('/api/knowledge/retrieve', { method: 'POST', body: JSON.stringify({ query: q, limit: 5 }) });
    $('#kbResult').textContent = res.hits.length
      ? res.hits.map((h) => `${h.citation}\nscore ${h.score}\n${h.text}\n`).join('\n────────\n')
      : 'Aucun résultat. Indexez la base Luau ou récupérez la documentation officielle.';
  } catch (e) { $('#kbResult').textContent = 'Erreur : ' + e.message; }
};

$('#kbSeed').onclick = async () => {
  $('#kbResult').textContent = 'Indexation de la base Luau…';
  try { $('#kbResult').textContent = JSON.stringify(await callTool('knowledge_index_luau', {}), null, 2); loadKnowledge(); }
  catch (e) { $('#kbResult').textContent = 'Erreur : ' + e.message; }
};

$('#kbDocs').onclick = async () => {
  $('#kbResult').textContent = 'Récupération de la documentation officielle (réseau requis)…';
  try { $('#kbResult').textContent = JSON.stringify(await callTool('knowledge_fetch_docs', {}), null, 2); loadKnowledge(); }
  catch (e) { $('#kbResult').textContent = 'Erreur : ' + e.message + '\nLa base Luau reste utilisable hors ligne.'; }
};

/* ---------------- agents ---------------- */

async function loadTasks() {
  const { tasks } = await api('/api/tasks');
  $('#taskList').innerHTML = tasks.length
    ? tasks.map((t) => `<div class="tool" data-id="${t.id}">
        <div class="name">${t.id}</div>
        <div class="meta">${t.status} · ${t.updated_at}</div>
        <div class="desc">${escapeHtml(t.goal)}</div>
      </div>`).join('')
    : '<p class="muted">Aucune tâche.</p>';
  $$('#taskList .tool').forEach((el) => (el.onclick = () => showTask(el.dataset.id)));
}

async function showTask(id) {
  try { $('#taskResult').textContent = JSON.stringify(await api('/api/tasks/' + id), null, 2); }
  catch (e) { $('#taskResult').textContent = 'Erreur : ' + e.message; }
}

$('#startTask').onclick = async () => {
  const goal = $('#goal').value.trim();
  if (!goal) return;
  $('#taskResult').textContent = 'Planification…';
  try {
    const res = await callTool('agent_start_task', { goal });
    $('#taskResult').textContent = JSON.stringify(res, null, 2);
    pollTask(res.taskId);
  } catch (e) { $('#taskResult').textContent = 'Erreur : ' + e.message; }
};

async function pollTask(id) {
  for (let i = 0; i < 60; i++) {
    await new Promise((r) => setTimeout(r, 1500));
    try {
      const st = await api('/api/tasks/' + id);
      $('#taskResult').textContent = JSON.stringify(st, null, 2);
      loadTasks();
      if (!['running', 'pending'].includes(st.status)) return;
    } catch { return; }
  }
}

/* ---------------- settings ---------------- */

async function loadSettings() {
  try {
    const h = await api('/api/health');
    $('#settingsCards').innerHTML =
      card('Niveau', 'L' + h.permissionLevel, '', '1 lecture · 2 assistance · 3 automatisation · 4 sensible') +
      card('Transport', h.transport) +
      card('Espace de travail', '', '', h.workspace) +
      card('Données', '', '', h.dataDir) +
      card('Outils', h.toolCount) +
      card('Sécurité', 'local uniquement', 'ok', 'token Bearer obligatoire');
    const { entries } = await api('/api/audit?limit=50');
    $('#auditDetail').textContent = entries.map((e) =>
      `${e.ts} · ${e.ok ? 'OK ' : 'ERR'} · L${e.level} · ${e.tool}${e.error ? ' · ' + e.error : ''}`).join('\n') || 'Vide.';
  } catch (e) {
    $('#settingsResult').textContent = 'Erreur : ' + e.message;
  }
}

$('#runDiagnostics').onclick = async () => {
  $('#settingsResult').textContent = 'Diagnostics…';
  try { $('#settingsResult').textContent = JSON.stringify(await api('/api/diagnostics', { method: 'POST' }), null, 2); }
  catch (e) { $('#settingsResult').textContent = 'Erreur : ' + e.message; }
};

$('#runSelfTest').onclick = async () => {
  $('#settingsResult').textContent = 'Auto-test des outils réels…';
  try { $('#settingsResult').textContent = JSON.stringify(await callTool('system_self_test', {}), null, 2); }
  catch (e) { $('#settingsResult').textContent = 'Erreur : ' + e.message; }
};

/* ---------------- utils + boot ---------------- */

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

async function refreshAll() {
  await loadDashboard();
  try { await loadTools(); } catch { /* token manquant */ }
}

async function boot() {
  await loadDashboard();
  try {
    await loadTools();
    await loadConnections();
    await loadExtension();
    await loadRoblox();
    await loadKnowledge();
    await loadTasks();
  } catch (e) {
    // Reported by the dashboard tab (token/connection problems).
  }
}

boot();
setInterval(() => { loadDashboard(); loadTasks(); }, 20000);
