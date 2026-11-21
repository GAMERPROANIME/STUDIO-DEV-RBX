# Architecture

OMNIBRIDGE est un **écosystème Python**. Le core Python détient toutes les décisions, la
mémoire, les outils et les permissions ; les autres langages ne sont que des interfaces
spécialisées vers leur environnement (navigateur, Roblox Studio, rendu web).

```
                        ┌──────────────────────────────────────────────────┐
   IA / clients MCP     │              OMNIBRIDGE CORE (Python)            │
   ─────────────────    │                                                  │
   Claude Desktop ──────┼─▶ mcp_server.py   MCPServer (SDK officiel v2)     │
   Claude Code     ─────┼─▶   · stdio            · Streamable HTTP /mcp    │
   Cursor / VS Code─────┼─▶   · resources        · prompts                  │
   hôte custom     ─────┼─▶ http_api.py     FastAPI /api/* + dashboard     │
                        │            │                                     │
   Dashboard (HTML/JS) ─┼────────────┘                                     │
                        │            ▼                                     │
                        │     core/app.py  OmniBridge.call_tool()          │
                        │            │                                     │
                        │   ┌────────┼──────────┬───────────┬───────────┐  │
                        │   ▼        ▼          ▼           ▼           ▼  │
                        │ registry  permissions  validation  db      audit │
                        │            │                                     │
                        │   ┌────────┴───────────┬──────────────┬────────┐ │
                        │   ▼                    ▼              ▼        ▼ │
                        │ agent/ (planner,   knowledge/       roblox/  tools/│
                        │  executor, roles)  engine+sources   luau+    (12  │
                        │                                    connector modules)
                        └───┬───────────────┬─────────────────┬──────────┘
                            │               │                 │
                   ┌────────▼──────┐ ┌──────▼───────┐ ┌───────▼──────────┐
                   │ SQLite        │ │ httpx +      │ │ MCP officiel      │
                   │ memory, FTS5, │ │ BeautifulSoup│ │ Roblox Studio     │
                   │ tasks, audit  │ │ (web docs)   │ │ (stdio, client)   │
                   └───────────────┘ └──────────────┘ └───────────────────┘

   Navigateur                              Windows / macOS / Linux
   ┌───────────────────────┐  native    ┌───────────────────────────────┐
   │ extension/ (JS MV3)   │◀──msg─────▶│ bridge/native_host.py         │
   │ modes manual/context/ │            │ (framing stdio, tool calls    │
   │ developer/research    │            │  uniquement, autostart core)  │
   └──────────┬────────────┘            └───────────────┬───────────────┘
              │ long-poll HTTP /bridge/*                │ Bearer token
              └───────────────────┬─────────────────────┘
                                  ▼
                         core Python (port 8765)
```

## Carte des modules

| Module | Rôle |
| --- | --- |
| `omnibridge/config.py` | configuration env/.env, token, chemins, niveau de permission |
| `omnibridge/core/app.py` | conteneur `OmniBridge` : câble tous les sous-systèmes, point d'entrée unique `call_tool` |
| `omnibridge/core/registry.py` | registre central des outils (`ToolDef`) |
| `omnibridge/core/permissions.py` | 4 niveaux, refus explicites, rédaction de secrets |
| `omnibridge/core/validation.py` | validation/coercition des arguments avant exécution |
| `omnibridge/core/sandbox.py` | confinement des chemins au workspace (y compris liens symboliques) |
| `omnibridge/core/db.py` | SQLite : mémoire, chunks + FTS5, tâches, checkpoints, audit |
| `omnibridge/core/logger.py` | logs JSON sur **stderr** (stdout réservé au JSON-RPC stdio) |
| `omnibridge/mcp_server.py` | `MCPServer`, génération des schémas, ressources, prompts, traduction des erreurs |
| `omnibridge/http_api.py` | FastAPI, auth Bearer, REST, dashboard, mount MCP, endpoints `/bridge/*` |
| `omnibridge/agent/planner.py` | planificateur déterministe (analyse du but → étapes réelles) |
| `omnibridge/agent/executor.py` | boucle asyncio : retries, timeouts, checkpoints, annulation, arrêt sur erreur répétée |
| `omnibridge/agent/roles.py` | 7 rôles d'agents (préférences d'outils, checklists) |
| `omnibridge/knowledge/engine.py` | chunking, FTS5 + TF-IDF, citations, stats |
| `omnibridge/knowledge/sources.py` | sources documentaires officielles, fetch httpx, HTML→texte |
| `omnibridge/roblox/luau.py` | analyseur statique Luau + base de connaissances embarquée |
| `omnibridge/roblox/connector.py` | client MCP du **Studio MCP officiel** (découverte, tools/list, call) |
| `omnibridge/tools/*.py` | 12 modules d'outils (system, files, code, web, knowledge, roblox, browser, bridge, agent, plugins, automation, project) |
| `omnibridge/bridge/native_host.py` | hôte Native Messaging Python (framing 4 octets + JSON) |
| `omnibridge/bridge/install.py` | enregistrement du host (Linux/macOS/Windows), manifests Chrome/Firefox |
| `omnibridge/studio_bridge/*` | **Studio Bridge** : `websocket_server` (127.0.0.1:17613), `security`, `process_manager`, `mcp_client` (SDK stdio), `tool_registry`, `roblox_connector` (6 états), `connection_manager`, `config`, `main` — voir [`STUDIO_BRIDGE.md`](STUDIO_BRIDGE.md) |
| `python_bridge/` | point d'entrée `python -m python_bridge` du Studio Bridge |
| `omnibridge/main.py` | CLI : `serve`, `diagnose`, `init`, `tools`, `call`, `test`, `webai`, `studio-bridge` |

## Deux chemins vers Roblox Studio (ne pas les confondre)

| Chemin | Qui parle à qui | Usage |
| --- | --- | --- |
| **Connecteur interne** (`omnibridge/roblox/connector.py`) | core Python → Studio MCP officiel | outils `roblox_*` de la CLI, du dashboard et des clients MCP natifs |
| **Studio Bridge** (`omnibridge/studio_bridge/`) | extension navigateur → pont Python → Studio MCP officiel | IA **web** (DeepSeek/Gemini/ChatGPT…), avec appairage et audit dédiés |

Les deux sont des **clients** du serveur MCP de Roblox : aucun ne réimplémente les outils de Studio.

## Flux d'un appel d'outil

1. Le transport (stdio MCP, HTTP MCP, REST `/api/tools/call`, CLI) reçoit `{name, args}`.
2. `OmniBridge.call_tool` : outil inconnu → erreur explicite ; `validate_args` applique les
   défauts et vérifie les types ; `check_permission` applique le niveau et `confirm` pour L4.
3. Le handler s'exécute avec un `ToolContext` (config, db, `call_tool`).
4. Résultat renvoyé tel quel (JSON sérialisé par le SDK), `audit` enregistré (succès/échec).
5. MCP : les exceptions contrôlées deviennent des erreurs d'outil lisibles ; les bugs
   deviennent des erreurs serveur journalisées avec traceback.

## Décisions techniques

| Décision | Justification |
| --- | --- |
| Python + asyncio | langage principal demandé, I/O concurrentes (MCP, HTTP, web, subprocess) |
| SDK MCP officiel v2 (`MCPServer`) | spec respectée, stdio + Streamable HTTP, resources/prompts, pas de protocole réinventé |
| FastAPI + Pydantic | validation, typage, OpenAPI, intégration ASGI avec le mount MCP |
| SQLite (stdlib) + FTS5 | zéro dépendance, requêtes lexicales rapides, fichiers locaux |
| TF-IDF maison pour le sémantique léger | évite une dépendance d'embeddings lourde ; retrieval hybride suffisant et explicable |
| httpx + BeautifulSoup | HTTP robuste, extraction HTML contrôlée |
| Aucune base vectorielle externe | simplicité de déploiement ; extension possible sans changer l'API d'outils |
| JavaScript uniquement extension | les API navigateur sont inaccessibles en Python : seul cas où JS est indispensable |
| Luau uniquement Studio | exécution in-Studio impossible autrement |
| Playwright optionnel | le pont d'extension est la voie principale ; Playwright comble les cas headless |

## Points d'extension

- **Nouvel outil** : `register(ToolDef(...))` dans un module `omnibridge/tools/` ; il apparaît
  automatiquement dans MCP, REST, CLI, dashboard et docs (`python tools/gen_tool_docs.py`).
- **Nouveau connecteur** : `plugins/<nom>/manifest.json` + `plugin_diagnose`.
- **Nouveau transport** : appeler `OmniBridge.call_tool` ; aucune logique métier hors du core.
