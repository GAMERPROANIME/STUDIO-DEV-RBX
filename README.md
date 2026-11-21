# OMNIBRIDGE AI — Universal MCP (Python core)

**Écosystème d'outils IA universel · moteur d'agents autonome · pont navigateur · intégration Roblox Studio**

OMNIBRIDGE transforme n'importe quelle IA compatible MCP (Claude Desktop, Claude Code,
Cursor, VS Code, ChatGPT/Codex, hôte personnalisé) en agent capable de **rechercher,
inspecter, construire, tester et corriger de vrais projets** — y compris des jeux Roblox
dans Studio — via **77 outils MCP réels**, un moteur de connaissances persistant et un
exécuteur multi-agents autonome.

> **Python-first.** Le core, le serveur MCP, les agents, le RAG, la mémoire, les
> diagnostics, le Desktop Bridge et les connecteurs sont en Python. JavaScript n'existe
> que pour l'extension navigateur, Luau que pour Roblox Studio, HTML/CSS pour le dashboard.
> Chaque composant secondaire appelle le core Python par une interface documentée — aucun
> système concurrent, aucune fonctionnalité dupliquée.

> Aucun outil factice. Chaque outil est implémenté et testé, et déclare honnêtement quand
> son backend (Roblox Studio, extension navigateur, Playwright) n'est pas connecté.

## Démarrage ultra simple (sans être ingénieur)

1. **Télécharger** : [ZIP de la branche de développement](https://codeload.github.com/GAMERPROANIME/STUDIO-DEV-RBX/zip/refs/heads/arena/06334a9a-studio-dev-rbx) → décompresser.
2. **Double-clic** : `DEMARRER-WINDOWS.bat` (Windows) ou `DEMARRER-MAC-LINUX.command` (Mac/Linux).
3. **C'est tout** : une page s'ouvre sur `http://127.0.0.1:17613` avec le code d'appairage,
   l'état de Roblox Studio en français et le bouton « Re-vérifier l'état ».

**Pour utiliser DeepSeek web avec Roblox Studio dès maintenant** : double-clic sur
`DEMARRER-PANNEAU-WINDOWS.bat` (ou `DEMARRER-PANNEAU-MAC-LINUX.command`), puis suis
[`DEEPSEEK_WEB_PAS_A_PAS.md`](DEEPSEEK_WEB_PAS_A_PAS.md) — panneau dans DeepSeek avec
**Connecter** (3 voyants : page, serveur, Studio) puis **Démarrer la boucle** : l'IA écrit, attend
sa réponse, exécute les outils dans Studio et renvoie les résultats toute seule (mode manuel en
secours).

Guides : [`DEMARRAGE_SIMPLE.md`](DEMARRAGE_SIMPLE.md) (dépannage, FAQ) ·
[`DEEPSEEK_WEB_PAS_A_PAS.md`](DEEPSEEK_WEB_PAS_A_PAS.md) ·
aperçu de la page locale : [`docs/apercu-page.html`](docs/apercu-page.html).

## Démarrage rapide (développeur)

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

omnibridge init                      # crée ~/.omnibridge, le token, indexe la base Luau
omnibridge diagnose                  # PASS/FAIL par sous-système
omnibridge                           # stdio + HTTP (dashboard http://127.0.0.1:8765)
```

Autres commandes :

```bash
omnibridge --transport http --port 8765   # HTTP + dashboard + MCP Streamable HTTP
omnibridge --stdio                        # MCP stdio uniquement (pour un client desktop)
omnibridge tools [--category roblox]      # catalogue réel des outils
omnibridge call --tool system_health      # appeler un outil en CLI
omnibridge call --tool process_run --args '{"action":"pytest"}' --confirm
omnibridge test                           # auto-test end-to-end des outils

python -m python_bridge                    # Studio Bridge : ws://127.0.0.1:17613 (extension ↔ Studio MCP)
omnibridge webai --prompt > prompt.txt     # ChatGPT/DeepSeek web : prompt à coller
omnibridge webai --run reponse.md          # exécute les appels du modèle, rend les résultats
omnibridge webai --check https://…/mcp     # ChatGPT Developer Mode : vérifie l'endpoint public
python examples/openai-compatible-agent.py "Inspecte ce projet"   # DeepSeek/OpenAI/Ollama API
```

Connexion d'un client IA : [`docs/CONNECT.md`](docs/CONNECT.md).
Token : `~/.omnibridge/token.txt` (généré au premier lancement, `chmod 600`).

## Ce que contient le projet

| Composant | Techno | Description |
| --- | --- | --- |
| **Core** | Python 3.11+ / asyncio | registre d'outils, permissions L1–L4, validation, SQLite, audit, sandbox |
| **Serveur MCP** | SDK MCP Python v2 (`MCPServer`) | stdio + Streamable HTTP, tools / resources / prompts, schémas générés depuis les signatures réelles |
| **Studio Bridge** | Python (`websockets` + SDK MCP) | **chaîne réelle** web → extension → `ws://127.0.0.1:17613` → serveur MCP officiel de Studio : jeton d'appairage, filtre d'origine, découverte dynamique, 6 états, audit |
| **Ponts IA** | Python + extension | **Panneau dans la page** (ChatGPT, DeepSeek, Gemini, Copilot, Grok), pont presse-papier, **Actions OpenAPI** (Custom GPT & Copilot Studio), API OpenAI-compatible (DeepSeek/Gemini/Grok/xAI/Ollama), MCP distant vérifié |
| **77 outils** | Python | system 4 · files 7 · project 2 · code 5 · knowledge 9 · web 5 · roblox 13 · browser 11 · bridge 2 · agent 10 · plugins 2 · automation 3 · webai 4 |
| **Moteur d'agents** | Python asyncio | plan → recherche → exécution → test → correction, checkpoints, reprise, annulation, 7 rôles |
| **Knowledge Engine** | SQLite FTS5 + TF-IDF | retrieval hybride avec citations (source, version, date, fiabilité), mémoire *personal / project / temp* |
| **Roblox Studio** | connecteur MCP officiel + Rojo | proxy du Studio MCP officiel + couche disque `.luau`, analyseur Luau, plugin complémentaire |
| **Desktop Bridge** | Python (Native Messaging) | hôte natif stdio ↔ core, commandes strictement limitées aux appels d'outils |
| **Extension navigateur** | JS (MV3 Chromium + Firefox) | modes manual / contextual / developer / research, long-poll `/bridge/*` |
| **Dashboard** | HTML/CSS/JS vanilla | Dashboard, MCP Explorer, AI Connections, Browser Extension, Roblox Studio, Knowledge Center, Agent Manager, Settings |
| **Sécurité** | Python | 4 niveaux, token Bearer, sandbox workspace, sauvegardes, rédaction de secrets, audit |

## Mission d'exemple

> *« Crée-moi un jeu Roblox de combat arène avec 3 armes et un système de progression. »*

L'agent inspecte le projet → recherche la documentation Roblox → planifie → construit les
systèmes Luau → analyse et teste → corrige → présente un rapport sourcé. Un exemple jouable
complet est fourni dans [`examples/roblox-combat-game/`](examples/roblox-combat-game/README.md).

## Documentation

| Document | Contenu |
| --- | --- |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | architecture Python, carte des modules, flux de communication |
| [`docs/CONNECT.md`](docs/CONNECT.md) | connecter Claude Desktop/Code, Cursor, VS Code, clients HTTP |
| [`docs/TOOLS.md`](docs/TOOLS.md) | catalogue **généré** des 72 outils (niveaux, paramètres) |
| [`docs/SECURITY.md`](docs/SECURITY.md) | modèle de permissions, sandbox, secrets, audit |
| [`docs/ROBLOX.md`](docs/ROBLOX.md) | Studio MCP officiel, Rojo, plugin, workflow de test |
| [`docs/EXTENSION.md`](docs/EXTENSION.md) | extension, modes, Desktop Bridge, dépannage |
| [`docs/WEB_AI.md`](docs/WEB_AI.md) | **ChatGPT, DeepSeek, Gemini, Copilot, Grok web** : 4 voies testées, installation, limites |
| [`docs/STUDIO_BRIDGE.md`](docs/STUDIO_BRIDGE.md) | **Studio Bridge** : architecture web → extension → Python → MCP Officiel, protocole WS, sécurité, 6 états, feuille de route |
| [`desktop-bridge/README.md`](desktop-bridge/README.md) | protocole Native Messaging et installation |

## Tests

```bash
python -m pytest            # 133 tests : core, outils, agents, MCP, HTTP, bridge, Luau, Actions, ponts IA, Studio Bridge
python -m omnibridge test   # auto-test runtime des outils
python -m omnibridge diagnose
```

Les tests couvrent le protocole MCP réel (stdio et Streamable HTTP), la boucle autonome
complète, la persistance, les refus de permission, le sandbox, le pont navigateur et le Studio
Bridge (client MCP réel, découverte, timeouts, sécurité WebSocket de bout en bout).

## Licence

MIT — voir [`LICENSE`](LICENSE).
