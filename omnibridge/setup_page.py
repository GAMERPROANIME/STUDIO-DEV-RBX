"""Guided setup page for the in-page panel (option A): `GET /demarrer`.

Target audience: someone who is not an engineer. One local page, four numbered steps, no
command line, no jargon. It is served by the *core* server (default port 8765), which is the
server the browser extension talks to.

Security, identical in spirit to the Studio Bridge page:
  * the token is shown only for a request typed in the address bar (no `Origin`,
    `Sec-Fetch-Mode` not `cors`/`no-cors`, `Sec-Fetch-Site` = `none`);
  * strict CSP, `X-Frame-Options: DENY`, `Cache-Control: no-store`, `Referrer-Policy`;
  * the page never talks to Roblox directly: it calls the local, token-protected API.
"""
from __future__ import annotations

import html
import json

from .studio_bridge.status_page import should_reveal_token  # same policy, single implementation

__all__ = ["build_setup_page", "should_reveal_token"]

_PAGE = """<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>OMNIBRIDGE — Brancher DeepSeek sur Roblox Studio</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body { margin: 0; font: 16px/1.55 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
         background: #0e1116; color: #e6edf3; }
  main { max-width: 760px; margin: 0 auto; padding: 28px 20px 60px; }
  h1 { font-size: 25px; margin: 0 0 4px; }
  h2 { font-size: 18px; margin: 0 0 6px; display: flex; gap: 10px; align-items: center; }
  .num { display: inline-flex; width: 26px; height: 26px; border-radius: 50%;
         background: #1f6feb; color: #fff; font-size: 15px; align-items: center;
         justify-content: center; flex: 0 0 auto; }
  .sub { color: #8b98a5; margin: 0 0 22px; }
  .card { background: #161b22; border: 1px solid #26303b; border-radius: 12px;
          padding: 18px 20px; margin: 0 0 16px; }
  .status { display: flex; gap: 12px; align-items: flex-start; }
  .dot { width: 12px; height: 12px; border-radius: 50%; margin-top: 7px; flex: 0 0 auto; }
  .ok { background: #2ea043; } .warn { background: #d29922; } .error { background: #f85149; }
  code, .token, .pill { font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; }
  .token { display: block; background: #0b0f14; border: 1px solid #26303b; border-radius: 8px;
           padding: 12px; font-size: 14px; word-break: break-all; user-select: all; }
  .pill { display: inline-block; background: #0b0f14; border: 1px solid #26303b;
          border-radius: 6px; padding: 3px 8px; font-size: 14px; }
  ol, ul { margin: 6px 0 0; padding-left: 22px; } li { margin-bottom: 8px; }
  a.btn, button { display: inline-block; background: #1f6feb; color: #fff; border: 0;
                  border-radius: 8px; padding: 9px 16px; font-size: 15px; cursor: pointer;
                  text-decoration: none; }
  a.btn.ghost, button.ghost { background: #21262d; color: #e6edf3; border: 1px solid #30363d; }
  .row { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 12px; }
  .muted { color: #8b98a5; font-size: 14px; }
  .kbd { background: #21262d; border: 1px solid #30363d; border-radius: 5px; padding: 1px 6px;
         font-family: ui-monospace, monospace; font-size: 13px; }
  table { width: 100%; border-collapse: collapse; font-size: 15px; }
  td { padding: 7px 0; border-bottom: 1px solid #21262d; vertical-align: top; }
  td:first-child { width: 130px; color: #b7c2cd; }
  details { margin-top: 8px; } summary { cursor: pointer; color: #8b98a5; }
  pre { background: #0b0f14; border: 1px solid #26303b; border-radius: 8px; padding: 12px;
        overflow: auto; font-size: 13px; }
</style>
</head>
<body>
<main>
  <h1>Brancher DeepSeek sur Roblox Studio</h1>
  <p class="sub">Tout se passe sur ton ordinateur. Rien n'est envoyé à un serveur OMNIBRIDGE :
     il n'y en a pas. Adresse locale : <code>@@server_url@@</code></p>

  <div class="card">
    <div class="status">
      <span class="dot @@level@@" id="dot"></span>
      <div>
        <h2 id="stateTitle" style="display:block">@@title@@</h2>
        <p id="stateHint" style="margin:0;color:#b7c2cd">@@hint@@</p>
      </div>
    </div>
    <div class="row">
      <button class="ghost" id="testBtn">Tester la connexion</button>
      <a class="btn ghost" href="/" target="_blank" rel="noreferrer">Ouvrir l'interface complète</a>
    </div>
  </div>

  <div class="card">
    <h2><span class="num">1</span> Installer l'extension dans ton navigateur</h2>
    <ol>
      <li>Ouvre Chrome (ou Edge) et tape <span class="kbd">chrome://extensions</span>
          dans la barre d'adresse.</li>
      <li>En haut à droite, active <strong>Mode développeur</strong> (l'interrupteur).</li>
      <li>Clique sur <strong>Charger l'extension non empaquetée</strong>.</li>
      <li>Choisis le dossier <code>extension</code> situé dans le dossier OMNIBRIDGE que tu as
          décompressé, puis <strong>Sélectionner un dossier</strong>.</li>
      <li>Épingle l'icône <strong>OMNIBRIDGE</strong> (puzzle en haut du navigateur).</li>
    </ol>
    <p class="muted">Firefox : <span class="kbd">about:debugging</span> → Ce Firefox →
       Charger un module temporaire → fichier <code>manifest.firefox.json</code>.</p>
  </div>

  <div class="card">
    <h2><span class="num">2</span> Coller ces deux informations dans l'extension</h2>
    <p class="muted" style="margin-top:0">Clique sur l'icône OMNIBRIDGE, puis remplis :</p>
    <table>
      <tr><td>Serveur local</td><td><span class="pill">@@server_url@@</span></td></tr>
      <tr><td>Code</td><td>@@token_block@@</td></tr>
    </table>
    <div class="row"><button id="copyBtn">Copier le code</button></div>
    <p class="muted">Puis clique sur <strong>« Connecter au core Python »</strong>. Le voyant doit
       passer au vert.</p>
  </div>

  <div class="card">
    <h2><span class="num">3</span> Utiliser DeepSeek</h2>
    <ol>
      <li>Va sur <a href="https://chat.deepseek.com/" target="_blank" rel="noreferrer">
          chat.deepseek.com</a> et ouvre une conversation.</li>
      <li>Un panneau <strong>OMNIBRIDGE</strong> apparaît en bas à droite (déplaçable).</li>
      <li>Clique <strong>Prompt</strong> → le texte est copié → colle-le dans le chat et envoie.</li>
      <li>Quand DeepSeek répond, clique <strong>Lire la réponse</strong> → <strong>Exécuter</strong>
          → <strong>Copier les résultats</strong>, et recolle-les dans le chat.</li>
    </ol>
    <table>
      <tr><td>Prompt</td><td>copie la liste des outils réels + le mode d'emploi</td></tr>
      <tr><td>Lire la réponse</td><td>extrait les appels d'outils du dernier message</td></tr>
      <tr><td>Exécuter</td><td>lance réellement les outils (donc Studio)</td></tr>
      <tr><td>Copier</td><td>copie les vrais résultats pour les rendre à DeepSeek</td></tr>
    </table>
  </div>

  <div class="card">
    <h2><span class="num">4</span> Roblox Studio</h2>
    <ol>
      <li>Ouvre Roblox Studio et une place (un jeu).</li>
      <li>Assistant → Réglages → MCP Servers → active
          <em>« Enable Studio as MCP server »</em>.</li>
      <li>Clique sur <strong>Tester la connexion</strong> en haut de cette page.</li>
    </ol>
    <p class="muted">Outils Roblox vus par le serveur : <span id="robloxState">…</span></p>
  </div>

  <details>
    <summary>Ça ne marche pas ?</summary>
    <table>
      <tr><td>Le panneau n'apparaît pas</td>
          <td>Vérifie que l'extension est activée et que le panneau flottant est coché dans
              l'icône OMNIBRIDGE.</td></tr>
      <tr><td>« token » refusé</td>
          <td>Recopie le code depuis cette page (bouton Copier), sans espace.</td></tr>
      <tr><td>Studio introuvable</td>
          <td>Studio doit être ouvert avec le serveur MCP activé ; sinon mets Studio à jour.</td></tr>
      <tr><td>Rien ne s'exécute</td>
          <td>La réponse de l'IA doit contenir un bloc JSON
              <code>{"calls":[…]}</code> : demande-lui « exécute maintenant ».</td></tr>
    </table>
    <pre>@@details@@</pre>
  </details>
</main>
<script>
(function () {
  var TOKEN = @@token_js@@;
  var dot = document.getElementById('dot');
  var title = document.getElementById('stateTitle');
  var hint = document.getElementById('stateHint');
  var robloxState = document.getElementById('robloxState');
  async function api(path) {
    var response = await fetch(path, {headers: {'Authorization': 'Bearer ' + TOKEN},
                                      cache: 'no-store'});
    if (!response.ok) throw new Error('HTTP ' + response.status);
    return response.json();
  }
  function setState(kind, text, advice) {
    dot.className = 'dot ' + kind;
    title.textContent = text;
    hint.textContent = advice || '';
  }
  async function check() {
    try {
      await api('/api/health');
      setState('ok', 'Le serveur local répond', 'Tu peux passer à l\\'étape 1.');
    } catch (e) {
      setState('error', 'Le serveur local ne répond pas',
               'Relance le fichier DEMARRER-PANNEAU (fenêtre noire).');
      return;
    }
    try {
      var info = await api('/api/roblox');
      if (info && info.available) {
        robloxState.textContent = (info.tools || []).length + ' outil(s) Studio connecté(s)';
        setState('ok', 'Prêt : DeepSeek peut piloter Studio', 'Suis les étapes 1 à 3.');
      } else {
        robloxState.textContent = (info && info.error) || 'Studio non connecté';
        setState('warn', 'Le serveur répond, Studio pas encore',
                 'Étape 4 : ouvre Studio et active le serveur MCP.');
      }
    } catch (e) { /* /api/roblox peut échouer sans Studio : on reste informatif */ }
  }
  var test = document.getElementById('testBtn');
  if (test) test.addEventListener('click', check);
  var copy = document.getElementById('copyBtn');
  if (copy) {
    copy.addEventListener('click', async function () {
      var value = document.getElementById('tokenValue');
      if (!value) return;
      try {
        await navigator.clipboard.writeText(value.textContent.trim());
        copy.textContent = 'Copié !';
      } catch (e) { copy.textContent = 'Sélectionne le code à la main'; }
    });
  }
  check();
})();
</script>
</body>
</html>
"""

_TOKEN_BLOCK = """<span class="token" id="tokenValue">@@token@@</span>"""

_TOKEN_HIDDEN = """<span class="muted">Pour afficher le code, ouvre cette page directement dans
    la barre d'adresse : <code>@@page_url@@</code> — ou lis-le dans la fenêtre noire du serveur.</span>"""


def build_setup_page(*, server_url: str, token: str | None, studio_state: str,
                     studio_detail: str, tool_count: int, reveal: bool,
                     page_url: str | None = None) -> str:
    from .studio_bridge.status_page import human_state

    page_url = page_url or server_url.rstrip("/") + "/demarrer"
    if reveal and token:
        title, hint, level = ("Le serveur local est prêt",
                              "Suis les 4 étapes ci-dessous : DeepSeek pourra alors piloter "
                              "Roblox Studio.", "ok")
        token_block = _TOKEN_BLOCK.replace("@@token@@", html.escape(token))
        token_js = json.dumps(token)
    else:
        title, hint, level = ("Le serveur local est prêt",
                              "Le code d'accès est masqué : ouvre cette page dans la barre "
                              "d'adresse pour le voir.", "ok")
        token_block = _TOKEN_HIDDEN.replace("@@page_url@@", html.escape(page_url))
        token_js = json.dumps("")

    if studio_state and studio_state != "ready":
        _state_title, state_hint, _level = human_state(studio_state)
        hint = f"{hint} Studio : {state_hint}"
    details = json.dumps({"server": server_url, "studioState": studio_state,
                          "studioDetail": studio_detail, "studioToolCount": tool_count,
                          "tokenShown": bool(reveal)}, indent=2, ensure_ascii=False)
    page = _PAGE
    for key, value in {
        "server_url": html.escape(server_url),
        "title": html.escape(title),
        "hint": html.escape(hint),
        "level": level,
        "token_block": token_block,
        "token_js": token_js,
        "details": html.escape(details),
    }.items():
        page = page.replace(f"@@{key}@@", value)
    return page
