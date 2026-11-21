# Sécurité

## Modèle de permissions (4 niveaux)

| Niveau | Nom | Ce qui est autorisé | Exemple |
| --- | --- | --- | --- |
| **1** | Lecture | inspection sans effet de bord | `file_read`, `code_analyze`, `web_search`, `roblox_inspect_project` |
| **2** | Assistance | validation, tests, indexation, sauvegardes | `code_test`, `knowledge_index`, `file_backup`, `agent_start_task` |
| **3** | Automatisation contrôlée | écritures avec sauvegarde, tâches, installateur de bridge | `file_update`, `roblox_edit_scripts`, `browser_*`, `desktop_bridge_install` |
| **4** | Sensible | irréversible, externe ou coûteux → `confirm=true` **à chaque appel** | `process_run`, `file_delete` |

Le niveau global se règle par `OMNIBRIDGE_PERMISSION_LEVEL` (défaut **2**). Un outil dont
le niveau dépasse la configuration est **refusé**, pas silencieusement dégradé :

```
permission denied: Tool "process_run" requires permission level 4,
but the server is configured for level 2.
```

## Secrets et données

- Token local `~/.omnibridge/token.txt`, `chmod 600`, généré avec `secrets.token_hex(32)`.
- Comparaison en temps constant (`secrets.compare_digest`).
- Rédaction automatique des motifs de secrets (`api_key=`, `password:`, `ghp_…`, `sk-…`,
  `AKIA…`) avant écriture de contenu ou de mémoire.
- Aucune lecture de cookies, mots de passe, champs de formulaire ou `localStorage`
  d'authentification par l'extension.
- Mémoire séparée en portées `personal`, `project`, `temp` — jamais de secrets dans la
  mémoire projet.

## Sandbox du système de fichiers

`sandbox_resolve` confine toute opération au workspace :

- chemins relatifs résolus sous la racine ;
- `..` neutralisé lexicalement ;
- chemins absolus hors workspace refusés ;
- liens symboliques dont la cible sort du workspace refusés.

Toute modification (`file_update`, `file_delete`, `roblox_edit_scripts`) crée une sauvegarde
horodatée dans `<data>/backups/` avant écriture, et la retourne dans la réponse
(`"backup": "..."`).

## Réseau

- Le serveur écoute par défaut sur `127.0.0.1` : **non joignable depuis l'extérieur**.
- Pour exposer à distance : reverse proxy TLS + token, ou tunnel authentifié. Ne jamais
  exposer `0.0.0.0` en clair : le token circule en en-tête.
- `OMNIBRIDGE_WEB_ALLOWED_HOSTS` restreint les domaines accessibles à `web_open`,
  `web_extract`, `web_compare_sources` (liste blanche optionnelle).
- Timeouts, taille maximale de fichier et de réponse sont bornés (`OMNIBRIDGE_MAX_FILE_BYTES`).

## Contenu non fiable

Le contenu web, les pages navigateur, les fichiers de dépôt et la documentation sont
**des données**, jamais des instructions :

- chaque réponse de `web_*` / `browser_*` porte un avertissement `UNTRUSTED ...` ;
- ce contenu ne peut pas élever une permission, modifier la configuration, ni autoriser un
  appel : la décision reste dans `check_permission` ;
- les prompts MCP rappellent explicitement la règle aux modèles.

## Isolation des composants secondaires

| Composant | Portée | Ce qu'il ne peut pas faire |
| --- | --- | --- |
| Extension (JS) | lit l'onglet actif sur commande du core | décider d'envoyer des données, lire les secrets, élargir les permissions |
| Desktop Bridge (Python) | transmet des **appels d'outils** au core | requêtes HTTP arbitraires, exécution de commandes, accès fichier direct |
| Plugin Roblox (Luau) | communique avec le bridge local | contourner le core, exécuter hors Studio |
| Dashboard (JS) | appelle `/api/*` avec le token | accéder aux fichiers du disque |

Le pont Native Messaging n'accepte que `ping | status | tools | health | call` ; toute autre
commande (`http`, `exec`, `shell`) est rejetée sans appel réseau.

## Audit

Chaque appel d'outil produit une entrée `audit` (horodatage, outil, niveau, succès/échec,
message d'erreur tronqué) :

```bash
omnibridge call --tool system_audit_log --args '{"limit":20}'
```

Le dashboard (Settings) et l'API `GET /api/audit` l'exposent. Les refus de permission y
figurent aussi.

## Bonnes pratiques recommandées

1. Rester en **niveau 2** par défaut ; monter à 3/4 pour une session de build explicite.
2. Relire la sauvegarde avant d'accepter une suppression (`file_delete`).
3. Utiliser un workspace dédié par projet (`OMNIBRIDGE_WORKSPACE`).
4. Ne jamais coller le token dans un prompt ou un dépôt public.
5. Vérifier `system_diagnostics` après chaque changement d'environnement.
