# Studio Bridge — ChatGPT/DeepSeek/Gemini web → Studio Roblox (chaîne locale réelle)

Ce document décrit la **nouvelle architecture** d'exécution d'OMNIBRIDGE : celle qui permet à une
IA **web** (DeepSeek, Gemini, ChatGPT, Kimi, GLM, Qwen, Arena, Meta AI…) de piloter **réellement**
Roblox Studio, sans jamais simuler d'outil et sans qu'une page web puisse parler à `localhost`.

Statut : **Milestone 1 terminé et testé** (pont Python). Milestones 2–8 : voir
[Feuille de route](#feuille-de-route).

---

## 1. Pourquoi trois composants (et pas un serveur HTTP)

| Fait vérifié | Conséquence architecturale |
| --- | --- |
| Une page web ne peut pas ouvrir `ws://127.0.0.1` ni appeler `http://localhost` (mixed content, Private Network Access, CSP) | il faut un composant **dans le navigateur** : l'extension |
| Une page web ne peut pas être client MCP | il faut un **pont hors navigateur** qui parle MCP |
| Roblox fournit **son propre** serveur MCP local (stdio) | OMNIBRIDGE est **client MCP** de ce serveur ; il ne le réimplémente pas |
| Le serveur MCP de Studio est un sous-processus stdio | il faut un process manager + un client SDK officiel |

```
  Page web (DeepSeek, Gemini, ChatGPT, Kimi, GLM, Qwen…)
        │  DOM (composer + bouton d'envoi) — adaptateur par plateforme
        ▼
  Extension navigateur (MV3) ── service worker ──┐
        │  ws://127.0.0.1:17613 (JSON, jeton d'appairage)
        ▼                                        │
  Studio Bridge (Python)  ← le cerveau            │  aucune page web
        │  MCP stdio (SDK officiel, client)      │  ne touche ce socket
        ▼                                        │
  Serveur MCP officiel de Roblox Studio ─────────┘
        ▼
  Roblox Studio (place ouverte)
```

Aucun de ces trois maillons ne peut être remplacé par « un serveur HTTP simple » ou une API
fictive : chacun couvre une contrainte que les deux autres ne peuvent pas lever.

---

## 2. Composants livrés (Milestone 1)

| Module | Rôle |
| --- | --- |
| `omnibridge/studio_bridge/config.py` | hôte/port/jeton/limites/niveaux, chemins par OS, `load_config()` (env + surcharges CLI) |
| `omnibridge/studio_bridge/security.py` | jeton d'appairage (comparaison à temps constant), politique d'origine, validation JSON Schema, niveaux L1–L4, rate limit, audit JSONL, rédaction de secrets |
| `omnibridge/studio_bridge/process_manager.py` | découverte et lancement du serveur MCP **de Roblox** (Windows / macOS / Linux), diagnostics honnêtes si absent |
| `omnibridge/studio_bridge/mcp_client.py` | client MCP réel : `stdio_client` + `ClientSession`, handshake, `tools/list`, `tools/call`, file d'attente interne, timeouts, reconnexion, arrêt propre |
| `omnibridge/studio_bridge/tool_registry.py` | registre **dynamique** (jamais de liste d'outils codée en dur), manifeste + bloc de prompt généré |
| `omnibridge/studio_bridge/roblox_connector.py` | machine à états à **6 états** déduits de preuves, rafraîchissement, redémarrage |
| `omnibridge/studio_bridge/connection_manager.py` | orchestration : permissions, validation, concurrence, timeouts, erreurs structurées, audit, statistiques |
| `omnibridge/studio_bridge/websocket_server.py` | serveur WS `127.0.0.1` uniquement, filtre d'origine à l'upgrade, `hello` obligatoire, actions, événements poussés |
| `omnibridge/studio_bridge/protocol.py` | version de protocole et catalogue d'actions |
| `omnibridge/studio_bridge/main.py` | composition root, CLI, logs rotatifs, boucle de rafraîchissement, arrêt par signal |
| `python_bridge/` | point d'entrée `python -m python_bridge` (délègue au paquet installé) |

---

## 3. Démarrage

```bash
pip install -e ".[dev]"                 # websockets est une dépendance réelle
python -m python_bridge --print-token    # jeton d'appairage (ou ~/.omnibridge/studio_bridge_token.txt)
python -m python_bridge                  # ws://127.0.0.1:17613
# équivalents : python -m omnibridge.studio_bridge · omnibridge studio-bridge
```

Options utiles :

```bash
python -m python_bridge --check                       # état JSON (lancement MCP, état, niveau)
python -m python_bridge --permission-level 1           # lecture seule
python -m python_bridge --studio-command "C:\\…\\mcp.bat" --studio-arg=--verbose
ROBLOX_STUDIO_MCP_COMMAND=… ROBLOX_STUDIO_MCP_ARGS="…" python -m python_bridge
```

Sur Windows, le binaire n'est pas à chercher : OMNIBRIDGE lance
`cmd.exe /c %LOCALAPPDATA%\Roblox\mcp.bat`. Sur macOS :
`/Applications/RobloxStudio.app/Contents/MacOS/StudioMCP`. Sur Linux, Roblox ne fournit rien :
il faut passer `--studio-command` (ou `ROBLOX_STUDIO_MCP_COMMAND`). **Sans ce serveur, aucun
outil Roblox n'existe** — le pont l'affiche au lieu d'inventer.

Vérification hors navigateur (double aussi de référence de protocole) :

```bash
python examples/studio_bridge_client.py --list
python examples/studio_bridge_client.py --call get_studio_state --args '{"studio_id":"abc"}'
```

---

## 4. Protocole (version 1)

Trames JSON texte, un objet par trame. `id` corrèle requête et réponse.

**Client → pont**

```json
{"id":"1","type":"hello","token":"<jeton>","client":"omnibridge-extension/1.0"}
{"id":"2","action":"status"}
{"id":"3","action":"ping"}
{"id":"4","action":"list_tools","refresh":true}
{"id":"5","action":"call_tool","tool":"<outil réel>","arguments":{…},"timeout":90}
{"id":"6","action":"studio_status","refresh":true}
{"id":"7","action":"restart_mcp"}
{"id":"8","action":"stop_task","task":"<id d'un call_tool>"}
{"id":"9","action":"tools_prompt","refresh":true}
{"id":"10","action":"audit_tail","limit":20}
```

**Pont → client**

```json
{"id":"1","type":"hello_ok","protocol":1,"bridge":{…},"tools":[…],"permissionLevel":3}
{"id":"5","ok":true,"action":"call_tool","result":{"isError":false,"text":"…","result":"…","tool":"…","elapsed":0.002}}
{"id":"5","ok":false,"action":"call_tool","error":{"code":"permission_denied","message":"…","detail":"…"}}
{"type":"event","event":"mcp_state","data":{"state":"ready", …}}
```

Codes d'erreur : `unknown_tool`, `invalid_arguments`, `permission_denied`, `not_connected`,
`timeout`, `rate_limited`, `tool_failed`, `busy`, `unknown_action`, `bad_request`, `internal_error`,
`unauthorized`, `cancelled`.

Fermetures : `4001` jeton invalide · `4002` protocole incorrect · `4003` `hello` trop lent.

---

## 5. Sécurité (7 couches)

1. **Loopback strict** — `BridgeConfig.validate()` refuse tout hôte autre que `127.0.0.1`.
2. **Filtre d'origine à l'upgrade HTTP** — seules les origines d'extension
   (`chrome-extension://`, `moz-extension://`, `safari-web-extension://`) passent ; une page web
   reçoit `403` *avant* l'ouverture du WebSocket.
3. **Appairage** — première trame `hello` obligatoire avec jeton de 64 caractères hexadécimaux,
   comparaison `secrets.compare_digest`, délai maximum de 5 s, fichier `chmod 600`.
4. **Validation stricte** — objet JSON uniquement, taille maximale (`512 Kio` par défaut, fermeture
   `1009` au-delà), action dans une liste fermée, arguments validés contre le **schéma publié par
   le serveur MCP** (`required`, types, `enum`, `additionalProperties`).
5. **Permissions** — niveau par outil (déduit du nom/description réels), refus si supérieur au
   niveau du pont, liste blanche optionnelle `OMNIBRIDGE_ALLOWED_TOOLS`.
6. **Limites** — `4` appels concurrents, `240` appels/minute, timeouts par appel, file d'attente
   interne au client MCP (`shield` : un timeout ne corrompt pas la session stdio).
7. **Audit** — `~/.omnibridge/studio_bridge_audit.jsonl` (connexions, refus, appels, résultats,
   erreurs) + logs rotatifs, secrets rédigés (`sk-…`, `ghp_…`, `api_key=…`).

Rien ne lit les cookies, les mots de passe ou les jetons des sites d'IA ; rien ne contourne les
protections des plateformes.

---

## 6. Découverte des outils (jamais codée en dur)

1. Lancement du serveur MCP officiel → handshake `initialize` (timeout `20 s`).
2. `tools/list` avec **backoff progressif** (`6` tentatives, `0.8 s × n`) : une liste vide n'est
   **pas** un échec, c'est souvent Studio encore en train de démarrer.
3. Le registre est reconstruit à chaque changement ; un diff détecté par la boucle de
   rafraîchissement (25 s) republie l'événement `mcp_state`.
4. Niveau de permission recalculé par outil ; noms/paramètres envoyés tels quels (aucune invention).
5. Si la liste reste vide après toutes les tentatives → état `no_tools`, jamais de faux outils.

---

## 7. Les 6 états de connexion

| État | Preuve | Ce que l'utilisateur doit faire |
| --- | --- | --- |
| `ready` | handshake OK + outils + Studio listé | rien |
| `studio_open_no_project` | handshake + outils, l'outil de listing renvoie `0` Studio | ouvrir une place `.rbxl` |
| `no_tools` | connecté, `tools/list` vide après toutes les tentatives | mettre Studio à jour |
| `mcp_disabled` | a répondu puis s'est arrêté | activer *Enable Studio as MCP server* |
| `mcp_unreachable` | commande trouvée, handshake en échec/timeout | redémarrer Studio puis `restart_mcp` |
| `studio_closed` | aucun serveur MCP lançable | installer/mettre à jour Studio ou renseigner la commande |

Chaque état porte un `hint` actionnable renvoyé à l'extension.

---

## 8. Tests (Milestone 1)

```bash
python -m pytest tests/test_studio_bridge.py -v
```

Le double de test `tests/fixtures/fake_studio_mcp.py` est un **vrai serveur MCP** (SDK, stdio) qui
expose des outils factices : il ne simule pas Roblox, il permet de tester le client MCP sans Studio.
Il supporte `--empty-first` (liste vide puis remplie), `--no-tools` et `--exit-after N`.

Couverture (19 tests) : configuration et persistance du jeton, refus non-loopback, politique
d'origine, comparaison de jeton, rédaction, validation JSON Schema, niveaux, rate limit, audit,
registre dynamique, découverte du lanceur, découverte MCP réelle, retry après liste vide, état
`no_tools`, état `studio_closed`, timeouts + reprise + redémarrage, refus de permission, erreurs
d'arguments, `unknown_tool`, et un **test WebSocket de bout en bout** (origine web refusée `403`,
mauvais jeton `4001`, `hello_ok`, `ping`, `list_tools`, `call_tool`, `tools_prompt`, `stop_task`,
`audit_tail`, trames invalides, chemin inconnu `404`, `hello` trop lent `4003`) plus la CLI
`--print-token` / `--check`.

Preuves live (exécutées) : `403` sur origine web, `101` sur origine d'extension, `404` sur chemin
inconnu, `hello_ok` + `list_tools` + `call_tool` réels, journal d'audit écrit, arrêt propre.

---

## 9. Feuille de route

| Milestone | Contenu | Statut |
| --- | --- | --- |
| **1** | Pont Python : config, sécurité, process manager, client MCP, registre, états, WebSocket, CLI, tests | **✅ terminé** |
| 2 | Extension MV3 : service worker propriétaire du WebSocket, appairage, reconnexion, file, UI de statut | à faire |
| 3 | Adaptateurs par plateforme + envoi/réception réels (DeepSeek d'abord) | à faire |
| 4 | Moteur d'émulation d'appels d'outils (`[[OMNIBRIDGE_TOOL_CALL]]` / `[[OMNIBRIDGE_TOOL_RESULT]]`) | à faire |
| 5 | Boucle d'agent autonome (START/STOP, historique, reprise, anti-doublon, rappel, limite de contexte) | à faire |
| 6 | Autres plateformes web (ChatGPT, Gemini, Kimi, GLM, Qwen, Arena, Meta AI) | à faire |
| 7 | Permissions dans l'UI, journal lisible, réglages | à faire |
| 8 | Tests 1–11 avec preuves, documentation finale, robustesse | à faire |

Ce qui **n'est pas encore** branché, et ne sera pas présenté comme tel : aucun adaptateur de
plateforme web n'est relié à ce pont pour l'instant. Le pont est vérifiable dès maintenant avec
`examples/studio_bridge_client.py`, et l'extension des milestones 2–3 s'y connectera via
`ws://127.0.0.1:17613`.
