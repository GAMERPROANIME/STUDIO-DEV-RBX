"""Human-friendly setup page served on http://127.0.0.1:17613/ by the Studio Bridge.

Why it exists: the bridge must be usable by someone who is not an engineer. Instead of reading
logs, the user opens one local page that says, in plain language, what is working, what is
missing, and what to click next.

Safety:
  * the page never exposes the pairing token to a request that comes from another origin or from
    an extension (`Origin` / `Sec-Fetch-*` headers) — only a request typed in the address bar;
  * no CORS headers, `X-Frame-Options: DENY`, strict CSP, `Cache-Control: no-store`;
  * `/status.json` never contains the token.
"""
from __future__ import annotations

import html
import json
from typing import Any

STATE_FR: dict[str, tuple[str, str, str]] = {
    "ready": (
        "Roblox Studio est connecté",
        "Tout fonctionne : le pont parle au serveur MCP officiel de Studio.",
        "ok",
    ),
    "studio_open_no_project": (
        "Studio répond, mais aucune place n'est ouverte",
        "Ouvre un jeu (.rbxl) dans Roblox Studio, puis clique sur « Re-vérifier l'état ».",
        "warn",
    ),
    "no_tools": (
        "Studio répond mais n'expose aucun outil",
        "Mets Roblox Studio à jour, puis relance ce pont. Aucun outil n'est inventé.",
        "warn",
    ),
    "mcp_disabled": (
        "Le serveur MCP de Studio est désactivé",
        "Dans Studio : Assistant → Réglages → MCP Servers → active « Enable Studio as MCP "
        "server », puis clique sur « Re-vérifier l'état ».",
        "warn",
    ),
    "mcp_unreachable": (
        "Impossible de joindre le serveur MCP de Studio",
        "Redémarre Roblox Studio, rouvre la place, puis clique sur « Re-vérifier l'état ».",
        "error",
    ),
    "studio_closed": (
        "Roblox Studio (ou son serveur MCP) est introuvable",
        "Installe ou mets à jour Roblox Studio, ouvre-le et active le serveur MCP "
        "(Assistant → Réglages → MCP Servers).",
        "error",
    ),
}

_PAGE = """<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>OMNIBRIDGE — Pont Roblox Studio</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body { margin: 0; font: 16px/1.55 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
         background: #0e1116; color: #e6edf3; }
  main { max-width: 720px; margin: 0 auto; padding: 28px 20px 60px; }
  h1 { font-size: 24px; margin: 0 0 4px; }
  h2 { font-size: 18px; margin: 0 0 4px; }
  .sub { color: #8b98a5; margin: 0 0 24px; }
  .card { background: #161b22; border: 1px solid #26303b; border-radius: 12px;
          padding: 18px 20px; margin: 0 0 16px; }
  .status { display: flex; gap: 12px; align-items: flex-start; }
  .dot { width: 12px; height: 12px; border-radius: 50%; margin-top: 7px; flex: 0 0 auto; }
  .ok { background: #2ea043; } .warn { background: #d29922; } .error { background: #f85149; }
  .status p { margin: 0; color: #b7c2cd; }
  .label { font-size: 13px; text-transform: uppercase; letter-spacing: .06em;
           color: #8b98a5; margin: 0 0 8px; }
  code, .token { font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; }
  .token { display: block; background: #0b0f14; border: 1px solid #26303b; border-radius: 8px;
           padding: 12px; font-size: 14px; word-break: break-all; user-select: all; }
  ol { margin: 8px 0 0; padding-left: 22px; } li { margin-bottom: 6px; }
  a.btn, button { display: inline-block; background: #1f6feb; color: #fff; border: 0;
                  border-radius: 8px; padding: 9px 16px; font-size: 15px; cursor: pointer;
                  text-decoration: none; }
  a.btn.ghost, button.ghost { background: #21262d; color: #e6edf3; border: 1px solid #30363d; }
  .row { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 12px; }
  details { margin-top: 6px; } summary { cursor: pointer; color: #8b98a5; }
  pre { background: #0b0f14; border: 1px solid #26303b; border-radius: 8px; padding: 12px;
        overflow: auto; font-size: 13px; }
  .muted { color: #8b98a5; font-size: 14px; }
</style>
</head>
<body>
<main>
  <h1>Pont OMNIBRIDGE</h1>
  <p class="sub">Ce pont relie ton IA web à Roblox Studio, sans site tiers.
     Page locale : <code>@@page_url@@</code></p>

  <div class="card">
    <div class="status">
      <span class="dot @@level@@" id="dot"></span>
      <div>
        <h2 id="stateTitle">@@title@@</h2>
        <p id="stateHint">@@hint@@</p>
      </div>
    </div>
    <div class="row">
      <a class="btn" href="/?refresh=1">Re-vérifier l'état</a>
      <a class="btn ghost" href="/status.json">Détails techniques</a>
    </div>
  </div>

  <div class="card">
    <p class="label">1. Code d'appairage</p>
    @@token_block@@
  </div>

  <div class="card">
    <p class="label">2. Roblox Studio</p>
    <ol>
      <li>Ouvre Roblox Studio et une place (un jeu).</li>
      <li>Assistant → Réglages → MCP Servers → active
          <em>« Enable Studio as MCP server »</em>.</li>
      <li>Reviens ici et clique sur « Re-vérifier l'état ».</li>
    </ol>
  </div>

  <div class="card">
    <p class="label">3. Outils disponibles (@@tool_count@@)</p>
    @@tools_block@@
  </div>

  <details>
    <summary>Détails techniques</summary>
    <pre>@@details@@</pre>
  </details>
  <p class="muted">Le pont n'écoute que sur cette machine (127.0.0.1). Aucune page web ne peut
     s'y connecter : seules les extensions autorisées, avec le code d'appairage.</p>
</main>
<script>
(function () {
  var dot = document.getElementById('dot');
  var title = document.getElementById('stateTitle');
  var hint = document.getElementById('stateHint');
  var map = @@state_map@@;
  async function refresh() {
    try {
      var response = await fetch('/status.json', {cache: 'no-store'});
      var data = await response.json();
      var entry = map[data.state] || map['studio_closed'];
      dot.className = 'dot ' + entry[2];
      title.textContent = entry[0];
      hint.textContent = entry[1];
    } catch (e) { /* le pont s'est arrete : la page reste lisible */ }
  }
  setInterval(refresh, 8000);
  var copy = document.getElementById('copyBtn');
  if (copy) {
    copy.addEventListener('click', async function () {
      var value = document.getElementById('tokenValue');
      if (!value) return;
      try {
        await navigator.clipboard.writeText(value.textContent.trim());
        copy.textContent = 'Copié !';
      } catch (e) {
        copy.textContent = 'Sélectionne le code à la main';
      }
    });
  }
})();
</script>
</body>
</html>
"""

_TOKEN_BLOCK = """<span class="token" id="tokenValue">@@token@@</span>
    <div class="row"><button id="copyBtn">Copier le code</button></div>"""

_TOKEN_HIDDEN = """<p class="muted">Pour afficher le code, ouvre cette page directement dans la
    barre d'adresse de ton navigateur : <code>@@page_url@@</code> — ou lis-le dans la fenêtre du
    pont (<code>python -m python_bridge --print-token</code>).</p>"""


def human_state(state: str) -> tuple[str, str, str]:
    return STATE_FR.get(state, STATE_FR["studio_closed"])


def status_payload(status: dict[str, Any], tools: list[dict[str, Any]]) -> dict[str, Any]:
    """JSON without secrets — safe to fetch from the page itself."""
    studio = status.get("studio") or {}
    return {
        "ok": True,
        "state": studio.get("state") or status.get("state"),
        "hint": studio.get("hint", ""),
        "detail": studio.get("detail", ""),
        "connected": bool(status.get("connected")),
        "toolCount": status.get("toolCount", 0),
        "permissionLevel": status.get("permissionLevel"),
        "launchCommand": studio.get("launchCommand", ""),
        "tools": [{"name": tool.get("name"), "level": tool.get("level"),
                   "description": (tool.get("description") or "")[:140]} for tool in tools],
        "mcp": status.get("mcp", {}),
    }


def build_page(status: dict[str, Any], tools: list[dict[str, Any]], token: str | None,
               uri: str, page_url: str | None = None) -> bytes:
    if page_url is None:
        page_url = f"http://{uri.split('://', 1)[-1].rstrip('/')}/"
    studio = status.get("studio") or {}
    state = studio.get("state") or status.get("state") or "studio_closed"
    title, hint, level = human_state(state)
    if token:
        token_block = _TOKEN_BLOCK.replace("@@token@@", html.escape(token))
    else:
        token_block = _TOKEN_HIDDEN.replace("@@page_url@@", html.escape(page_url))
    if tools:
        tools_block = "<ul>" + "".join(
            f"<li><code>{html.escape(str(tool.get('name')))}</code> "
            f"<span class='muted'>(niveau {tool.get('level')})</span></li>"
            for tool in tools) + "</ul>"
    else:
        tools_block = ("<p class='muted'>Aucun pour l'instant : cette page n'affiche que les "
                       "outils réellement exposés par Roblox Studio. Rien n'est inventé.</p>")
    details = json.dumps({"bridge": status, "tools": [t.get("name") for t in tools]},
                         indent=2, ensure_ascii=False, default=str)
    values = {
        "page_url": html.escape(page_url),
        "title": html.escape(title),
        "hint": html.escape(hint),
        "level": html.escape(level),
        "token_block": token_block,
        "tool_count": str(len(tools)),
        "tools_block": tools_block,
        "details": html.escape(details),
        "state_map": json.dumps({key: list(value) for key, value in STATE_FR.items()},
                                ensure_ascii=False),
    }
    page = _PAGE
    for key, value in values.items():
        page = page.replace(f"@@{key}@@", value)
    return page.encode("utf-8")


def should_reveal_token(origin: str | None, sec_fetch_mode: str | None,
                        sec_fetch_site: str | None, user_agent: str = "") -> bool:
    """Only a page opened by hand (address bar) may display the pairing token."""
    if origin:
        return False  # another origin/extension is asking
    if (sec_fetch_mode or "").lower() in ("cors", "no-cors"):
        return False
    if (sec_fetch_site or "").lower() not in ("", "none"):
        return False
    return True
