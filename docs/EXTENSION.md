# Extension navigateur & Desktop Bridge

## Rôle

L'extension transmet au core Python **uniquement ce que l'utilisateur autorise** depuis
l'onglet actif. Elle exécute les commandes demandées par les outils `browser_*` ; elle ne
décide jamais d'envoyer quoi que ce soit d'elle-même et ne lit ni cookies, ni mots de passe,
ni champs de formulaire.

Deux chemins de communication, vers **le même core Python** :

```
extension ──long-poll HTTP /bridge/*──▶ core Python (port 8765)
extension ──native messaging──────────▶ bridge/native_host.py ──▶ core Python
```

## Installation (Chromium : Chrome, Edge, Brave, Chromium)

1. `chrome://extensions` → activer le **mode développeur**.
2. « Charger l'extension non empaquetée » → sélectionner le dossier `extension/`.
3. Noter l'ID affiché (nécessaire pour le Desktop Bridge).
4. Ouvrir le popup → coller le token (`~/.omnibridge/token.txt`) → choisir un mode →
   **Connecter**.

## Installation (Firefox)

1. Copier `extension/manifest.firefox.json` en `extension/manifest.json` (remplace la version
   Chromium ; `background.scripts` et `browser_specific_settings` sont adaptés).
2. `about:debugging` → « Ce Firefox » → « Charger un module temporaire » → `manifest.json`.
3. Mode permanent : empaqueter via `web-ext build` puis signer sur AMO.

## Modes

| Mode | Portée | Détail |
| --- | --- | --- |
| `manual` | fenêtre d'autorisation de 10 min | le popup doit être armé avant chaque session (« Autoriser 10 min ») |
| `contextual` | onglet actif | texte, sélection, liens, recherche, capture d'écran |
| `developer` | contextual + métadonnées | balises meta (hors secrets), scripts, compteurs, timings |
| `research` | lecture seule | capture et infos techniques **refusées** |

Le core applique aussi ses propres règles : chaque commande passe par un outil `browser_*`
de niveau 1 (lecture), quel que soit le mode.

## Panneau flottant sur les sites d'IA (sans MCP)

Le panneau s'injecte sur **chatgpt.com, chat.deepseek.com, gemini.google.com,
copilot.microsoft.com, grok.com**. Il a deux modes.

### Mode automatique (bouton « Connecter »)

| Élément | Effet |
| --- | --- |
| Voyant *Page IA* | adaptateur du site trouvé + zone de saisie + bouton d'envoi |
| Voyant *Serveur local* | `GET /api/health` (nombre d'outils, niveau de permission) |
| Voyant *Studio* | `GET /api/roblox` (serveur MCP officiel de Studio joignable) |
| **Démarrer la boucle** | écrit le prompt + ta demande dans le chat, attend que la réponse se stabilise, exécute les appels via `POST /api/webai/run`, renvoie le bloc de résultats, recommence |
| **Arrêter** | interrompt immédiatement |

Garde-fous : démarrage uniquement sur clic, 10 cycles maximum, timeout de réponse, arrêt sur
réponse finale, anti-doublon sur les appels, 2 échecs consécutifs = arrêt, journal visible dans
le panneau. Le code vit dans `extension/agent-loop.js` (boucle) et
`extension/site-adapters.js` (un adaptateur par plateforme : `detectProvider`, `findComposer`,
`findSendButton`, `readAssistantMessages`, `getLatestAssistantResponse`, `isGenerating`,
`sendMessage`, `observeConversation`, `getConversationId`, `getProviderStatus`).

### Mode manuel (replié dans le panneau)

| Bouton | Effet |
| --- | --- |
| Prompt | copie le prompt OMNIBRIDGE (catalogue réel) dans le presse-papier |
| Lire la réponse | lit la dernière réponse de l'assistant dans la page (adaptateurs par site) |
| Exécuter | exécute réellement les appels JSON via le core, copie le bloc de résultats |
| Copier | recopie le bloc à recoller |

Activation : popup → case « Panneau flottant sur ChatGPT / DeepSeek / Gemini / Copilot / Grok ».
Aucune lecture de cookies, de mots de passe ou de jetons de session, aucun serveur distant :
tout passe par `127.0.0.1` avec le token. Détails et dépannage : [`WEB_AI.md`](WEB_AI.md) et
[`../DEEPSEEK_WEB_PAS_A_PAS.md`](../DEEPSEEK_WEB_PAS_A_PAS.md).

## Outils navigateur

`browser_get_active_tab`, `browser_get_page_content`, `browser_get_selected_text`,
`browser_get_links`, `browser_search_page`, `browser_capture_page`, `browser_get_page_info`,
`browser_get_last_assistant_message`, `browser_status` — plus `browser_pw_status` /
`browser_pw_open` (Playwright optionnel).

Sans extension connectée, ces outils renvoient une erreur explicite contenant la procédure
d'installation : **aucune donnée de page n'est inventée**.

## Desktop Bridge (Native Messaging, Python)

```bash
python -m omnibridge.bridge.install --extension-id <ID_DE_L_EXTENSION>
python -m omnibridge.bridge.install --print        # afficher les manifests
python -m omnibridge.bridge.install --uninstall
```

Ou via l'outil MCP / dashboard : `desktop_bridge_install` (niveau 3),
`desktop_bridge_status` (niveau 1).

Détails du protocole et du registre par OS : [`../desktop-bridge/README.md`](../desktop-bridge/README.md).

Le host Python :
- démarre le core s'il ne répond pas (`OMNIBRIDGE_BRIDGE_AUTOSTART=0` pour désactiver) ;
- n'accepte que `ping | status | health | tools | call` ;
- rejette `http`, `exec`, `shell` — ce n'est pas un proxy ouvert.

## Vérification

```bash
omnibridge call --tool browser_status
omnibridge call --tool desktop_bridge_status
omnibridge call --tool browser_get_active_tab     # nécessite un onglet + extension connectée
```

Dans le navigateur : popup → « Statut du core » / « Lister les outils » (via le Desktop Bridge).

## Dépannage

| Symptôme | Solution |
| --- | --- |
| popup : « Non connecté » | core lancé ? `omnibridge --transport http` ; token correct ? |
| `HTTP 401` | token absent/erroné dans le popup |
| `Unknown or expired requestId` | commande expirée : relancer l'appel d'outil |
| `Native host unavailable` | `python -m omnibridge.bridge.install --extension-id <id>` puis redémarrer le navigateur |
| capture refusée | mode `research` — passer en `contextual` ou `developer` |
| commande refusée « Autorisation requise » | mode `manual` : cliquer « Autoriser 10 min » |

## Sécurité

- Mode `manual` par défaut : aucune lecture sans autorisation explicite.
- L'extension n'a pas d'accès disque ; le host n'a pas d'accès navigateur.
- Le contenu de page est marqué `UNTRUSTED` et ne peut pas modifier les permissions.
- Le token n'est jamais transmis aux pages web (stockage local de l'extension uniquement).
