'use strict';

const $ = (s) => document.querySelector(s);

function render(status) {
  const el = $('#status');
  el.innerHTML = '';
  const line = (text, cls) => {
    const div = document.createElement('div');
    if (cls) div.className = cls;
    div.textContent = text;
    el.appendChild(div);
  };
  line(`Serveur : ${status.server}`);
  line(status.connected ? `Connecté · client ${String(status.clientId).slice(0, 8)}…` : 'Non connecté', status.connected ? 'ok' : 'warn');
  line(`Mode : ${status.mode} · transport : ${status.transport}`);
  if (status.mode === 'manual') {
    const mins = status.authorized ? Math.max(0, Math.round((status.armedUntil - Date.now()) / 60000)) : 0;
    line(status.authorized ? `Autorisé encore ~${mins} min` : 'Autorisation requise : cliquez « Autoriser 10 min »', status.authorized ? 'ok' : 'warn');
  }
  if (!status.hasToken) line('Token manquant : le core refusera les requêtes (HTTP 401)', 'err');
  if (status.lastError) line(`Dernière erreur : ${status.lastError}`, 'err');
  $('#authorize').disabled = !status.connected;
}

async function refresh() {
  const stored = await chrome.storage.local.get(['server', 'token', 'mode', 'autoOpen']);
  $('#server').value = stored.server || 'http://127.0.0.1:8765';
  $('#token').value = stored.token || '';
  $('#mode').value = stored.mode || 'manual';
  const all = await chrome.storage.local.get(['autoOpen']);
  $('#autoOpen').checked = all.autoOpen !== false;
  render(await chrome.runtime.sendMessage({ type: 'status' }));
}

$('#connect').onclick = async () => {
  const res = await chrome.runtime.sendMessage({
    type: 'connect',
    server: $('#server').value.trim() || 'http://127.0.0.1:8765',
    token: $('#token').value.trim(),
    mode: $('#mode').value,
  });
  if (res.ok) render(res.status);
  else {
    $('#status').textContent = 'Échec : ' + res.error;
    $('#status').className = 'err';
  }
  refresh();
};

$('#authorize').onclick = async () => {
  const res = await chrome.runtime.sendMessage({ type: 'authorize', minutes: 10 });
  if (res.ok) render(res.status);
};

$('#disconnect').onclick = async () => {
  await chrome.runtime.sendMessage({ type: 'disconnect' });
  refresh();
};

$('#nativeStatus').onclick = async () => {
  const res = await chrome.runtime.sendMessage({ type: 'native_status' });
  $('#tools').textContent = res.ok
    ? JSON.stringify(res.result.core, null, 1).slice(0, 1500)
    : 'Desktop Bridge indisponible : ' + (res.error || '');
};

$('#nativeTools').onclick = async () => {
  const res = await chrome.runtime.sendMessage({ type: 'core_tools' });
  if (!res.ok) {
    $('#tools').textContent = 'Desktop Bridge indisponible : ' + (res.error || '');
    return;
  }
  const tools = (res.result.tools || []).map((t) => `L${t.level} ${t.name} — ${t.category}`);
  $('#tools').textContent = `${tools.length} outils\n` + tools.join('\n');
};

$('#autoOpen').onchange = async () => {
  await chrome.storage.local.set({ autoOpen: $('#autoOpen').checked });
};

$('#mode').onchange = async () => {
  await chrome.storage.local.set({ mode: $('#mode').value });
  if ($('#mode').value === 'manual') {
    await chrome.runtime.sendMessage({ type: 'authorize', minutes: 10 });
  }
  refresh();
};

refresh();
setInterval(refresh, 3000);
