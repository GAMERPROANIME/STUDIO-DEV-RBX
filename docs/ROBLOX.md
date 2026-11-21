# Intégration Roblox Studio

OMNIBRIDGE **ne réimplémente pas** les capacités natives de Studio. Il s'appuie sur le
**Studio MCP officiel de Roblox** (serveur MCP local fourni par Studio) et ajoute ce que
Studio ne fournit pas : orchestration, connaissances Luau, couche disque Rojo, analyse
statique, tests, diagnostic et boucle agentique.

## Deux couches complémentaires

| Couche | Quand | Outils |
| --- | --- | --- |
| **Studio MCP officiel** (Live) | Studio ouvert, serveur MCP activé | `roblox_list_studios`, `roblox_get_studio_state`, `roblox_inspect_instance`, `roblox_execute_luau`, `roblox_create_objects`, `roblox_playtest`, `roblox_get_console_output`, `roblox_capture_screen`, `roblox_search_assets` |
| **Rojo / disque** (Offline) | sans Studio, CI, revue de code | `roblox_inspect_project`, `roblox_search_scripts`, `roblox_read_script`, `roblox_edit_scripts`, `code_analyze`, `code_test`, `project_analyze` |

Les outils « Live » **délèguent** au serveur officiel : ils découvrent ses outils par
`tools/list` et les proxifient. Si le serveur n'est pas configuré, ils renvoient
`{"available": false, "setupInstructions": "..."}` — jamais de résultat fabriqué.

## Activer le Studio MCP officiel

1. Roblox Studio → **Assistant → Settings → MCP Servers** →
   activer « Enable Studio as MCP server ».
2. Ouvrir une place (le serveur est lié à la session Studio).
3. Indiquer à OMNIBRIDGE comment lancer le serveur :

```bash
# Windows
export ROBLOX_STUDIO_MCP_COMMAND="$LOCALAPPDATA/Roblox/mcp.bat"
# macOS
export ROBLOX_STUDIO_MCP_COMMAND="/Applications/RobloxStudio.app/Contents/MacOS/StudioMCP"
```

Découverte automatique : OMNIBRIDGE cherche ces emplacements par défaut ; sinon renseigner
la variable. Vérification :

```bash
omnibridge call --tool roblox_list_studios
omnibridge call --tool roblox_get_studio_state
```

Réponse attendue avec Studio ouvert : `available: true`, `officialTools: [...]`, et la liste
des studios. Sans Studio : `available: false` + instructions.

## Plugin complémentaire (Luau)

`roblox-plugin/OmniBridgePlugin.server.luau` s'installe dans Studio (Plugins Folder) et
communique avec le bridge HTTP local pour les actions complémentaires (sélection, exécution
de snippets, rapports d'analyse). Il ne duplique pas les outils officiels : il sert de pont
entre l'interface Studio et le core Python quand le Studio MCP n'est pas disponible.

## Workflow typique d'un agent

```
roblox_inspect_project                → arborescence, project.json, fichiers .luau
knowledge_retrieve "RemoteEvent"      → documentation citée
roblox_search_scripts "DataStore"     → code existant
agent_create_plan                     → étapes avec outils réels
roblox_edit_scripts / file_update     → écriture avec sauvegarde + analyse
code_analyze                          → services, classes, API dépréciées, délimiteurs
code_test                             → vérification statique (ou playtest si Studio connecté)
roblox_playtest / roblox_get_console_output → validation live
agent_review_result                   → bilan, corrections
```

## Analyseur Luau

`omnibridge/roblox/luau.py` vérifie :

- présence de `--!strict` ;
- appels `game:GetService("X")` contre une liste de services réels ;
- `Instance.new("X")` contre une liste de classes réelles ;
- API dépréciées (`wait`, `spawn`, `delay`, `Humanoid:LoadAnimation`, …) ;
- équilibrage des délimiteurs `()[]{}` avec numéros de ligne ;
- motifs de code risqué (client-side DataStore, etc.).

Chaque constat porte `severity`, `message`, `line` et est exploitable par l'agent.

## Exemple jouable

[`examples/roblox-combat-game/`](../examples/roblox-combat-game/README.md) : arène de combat
Rojo (config partagée, serveur autoritaire, client, gestion d'arène).

```bash
cd examples/roblox-combat-game
rojo serve            # puis « Connect » dans le plugin Rojo de Studio
```

Sans Rojo : copier les fichiers `.luau` dans des Scripts/LocalScripts/ModuleScripts
équivalents dans Studio.

## Limites assumées

- Le serveur MCP officiel appartient à Roblox : ses noms d'outils peuvent évoluer. OMNIBRIDGE
  les découvre dynamiquement et ne code pas en dur un nom unique — il cherche par motif et
  signale les outils réellement exposés.
- L'exécution de Luau live nécessite une session Studio authentifiée : impossible en CI.
- Pas de contournement de restrictions, pas d'accès aux cookies/tokens Roblox.
