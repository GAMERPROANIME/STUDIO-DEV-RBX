# Connecter un client IA

OMNIBRIDGE expose **un seul serveur MCP** avec deux transports :

| Transport | URL / commande | Auth | Usage |
| --- | --- | --- | --- |
| Streamable HTTP | `http://127.0.0.1:8765/mcp` | `Authorization: Bearer <token>` | clients distants de l'onglet, dashboard, plusieurs clients |
| stdio | `python -m omnibridge --stdio` | aucune (processus local) | Claude Desktop, IDE, agents locaux |

Le token est dans `~/.omnibridge/token.txt` (créé au premier lancement, permissions `600`).

```bash
omnibridge --transport http          # HTTP + dashboard + MCP HTTP
omnibridge --stdio                   # stdio seul, stdout réservé au JSON-RPC
omnibridge                           # les deux (stdio désactivé si stdin est un terminal)
```

## Claude Desktop

`claude_desktop_config.json` :

- macOS : `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows : `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "omnibridge": {
      "command": "python",
      "args": ["-m", "omnibridge", "--stdio"],
      "env": {
        "OMNIBRIDGE_WORKSPACE": "/chemin/vers/votre/projet",
        "OMNIBRIDGE_PERMISSION_LEVEL": "3"
      }
    }
  }
}
```

Redémarrez Claude Desktop : les 72 outils apparaissent dans la liste MCP.

## Claude Code / Cursor / VS Code (MCP)

```bash
# Claude Code
claude mcp add omnibridge -- python -m omnibridge --stdio

# Cursor / VS Code : ~/.cursor/mcp.json ou .vscode/mcp.json
```

```json
{
  "mcpServers": {
    "omnibridge": {
      "command": "python",
      "args": ["-m", "omnibridge", "--stdio"],
      "env": { "OMNIBRIDGE_WORKSPACE": "${workspaceFolder}" }
    }
  }
}
```

## Client HTTP (Streamable HTTP)

```json
{
  "mcpServers": {
    "omnibridge": {
      "type": "http",
      "url": "http://127.0.0.1:8765/mcp",
      "headers": { "Authorization": "Bearer VOTRE_TOKEN" }
    }
  }
}
```

Test manuel :

```bash
TOKEN=$(cat ~/.omnibridge/token.txt)
curl -s -X POST http://127.0.0.1:8765/mcp \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{
        "protocolVersion":"2025-11-25","capabilities":{},
        "clientInfo":{"name":"curl","version":"1"}}}'
```

Le protocole négocie la version supportée par le SDK (jusqu'à `2025-11-25`).

## Client Python (SDK officiel)

```python
import asyncio, httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

async def main():
    token = open("/home/USER/.omnibridge/token.txt").read().strip()
    async with httpx.AsyncClient(headers={"Authorization": f"Bearer {token}"}) as client:
        async with streamable_http_client("http://127.0.0.1:8765/mcp", http_client=client) as streams:
            read, write = streams[0], streams[1]
            async with ClientSession(read, write) as s:
                await s.initialize()
                print(len((await s.list_tools()).tools), "tools")
                res = await s.call_tool("system_health", {})
                print(res.content[0].text[:200])

asyncio.run(main())
```

## Ressources et prompts

| Type | URI / nom | Contenu |
| --- | --- | --- |
| resource | `omnibridge://tools/catalogue` | catalogue complet avec schémas JSON |
| resource | `omnibridge://system/info` | version, workspace, niveau, nombre d'outils |
| resource | `omnibridge://knowledge/luau` | base de connaissances Luau/Roblox embarquée |
| prompt | `roblox-game-mission` | mission de construction/débogage Roblox |
| prompt | `debug-workflow` | boucle de débogage structurée |

## Niveaux de permission

```bash
OMNIBRIDGE_PERMISSION_LEVEL=1   # lecture seule
OMNIBRIDGE_PERMISSION_LEVEL=2   # assistance (défaut) : lecture + tests + indexation
OMNIBRIDGE_PERMISSION_LEVEL=3   # automatisation contrôlée (écriture de fichiers, agents, tâches)
OMNIBRIDGE_PERMISSION_LEVEL=4   # sensible : process_run, file_delete (confirm=true obligatoire)
```

Un refus est explicite (`permission denied: ...`) et journalisé dans l'audit.

## Autres IA (ChatGPT web, DeepSeek web, Gemini, Copilot…)

Ces interfaces ne parlent pas MCP et ne peuvent pas joindre `localhost`. Trois chemins réels :

| Besoin | Commande |
| --- | --- |
| Chat web sans MCP (copier/coller) | `omnibridge webai --prompt` puis `omnibridge webai --run reponse.md` |
| API OpenAI-compatible (DeepSeek, OpenAI, Groq, Ollama) | `python examples/openai-compatible-agent.py "…"` |
| ChatGPT Developer Mode (MCP distant HTTPS) | tunnel + `omnibridge webai --check https://…/mcp` |

Détails, prérequis et limites : [`WEB_AI.md`](WEB_AI.md).

## Dépannage

| Symptôme | Cause / solution |
| --- | --- |
| `401 unauthorized` | token absent ou erroné → `cat ~/.omnibridge/token.txt` |
| stdout pollué / client stdio qui ferme | un `print()` a été ajouté dans le code : les logs doivent aller sur stderr |
| `Unknown tool` | le nom n'existe pas → `omnibridge tools` |
| `roblox_*` renvoie `available: false` | Studio MCP officiel non configuré → voir `docs/ROBLOX.md` |
| dashboard sans données | token non saisi dans le champ « Connecter » |
| port occupé | `omnibridge --transport http --port 8766` |
