# Rendre OMNIBRIDGE disponible sur DeepSeek web, Gemini, Copilot, Grok web

Ces interfaces n'exposent **pas** de client MCP et ne peuvent pas joindre `localhost`.
OMNIBRIDGE implémente donc **quatre voies réelles** — aucune ne dépend d'un contournement
des conditions d'utilisation, aucune ne lit vos cookies ou vos identifiants.

| Plateforme | Panneau dans la page | Pont presse-papier | Actions OpenAPI | API (clé perso) | MCP |
| --- | --- | --- | --- | --- | --- |
| **ChatGPT web** | ✅ | ✅ | ✅ Custom GPT Actions | ✅ OpenAI | ✅ distant (payant + tunnel) |
| **DeepSeek web** | ✅ | ✅ | ❌ pas d'actions custom | ✅ DeepSeek | ❌ |
| **Gemini** | ✅ | ✅ | ❌ (Gems sans actions) | ✅ endpoint OpenAI-compat | ❌ (Gemini CLI, lui, est client MCP) |
| **Copilot** | ✅ | ✅ | ✅ Copilot Studio | ❌ API consommateur publique | ❌ |
| **Grok web** | ✅ | ✅ | ❌ | ✅ API xAI | ❌ |
| Ollama / LM Studio | — | — | — | ✅ local, sans clé | — |
| Claude Desktop/Code, Cursor, VS Code | — | — | — | — | ✅ automatique |

---

## 1. Panneau flottant dans la page (le plus rapide à l'usage)

Le panneau s'injecte sur **chatgpt.com, chat.deepseek.com, gemini.google.com,
copilot.microsoft.com, grok.com** et propose quatre boutons :

| Bouton | Effet |
| --- | --- |
| **Prompt** | récupère le prompt système auprès du core et le copie (catalogue réel inclus) |
| **Lire la réponse** | lit la dernière réponse de l'assistant dans la page (adaptateurs par site, sinon sélection manuelle) |
| **Exécuter** | envoie cette réponse au core : les appels JSON sont réellement exécutés, le bloc de résultats est copié |
| **Copier** | recopie le bloc de résultats pour le recoller dans la conversation |

Installation :

1. `omnibridge --transport http` (le core doit tourner).
2. `chrome://extensions` → mode développeur → « Charger l'extension non empaquetée » → dossier `extension/`.
3. Popup de l'extension : coller le token (`~/.omnibridge/token.txt`), cocher
   « Panneau flottant sur ChatGPT / DeepSeek / Gemini / Copilot / Grok », **Connecter**.
4. Recharger la page de chat : le panneau ◈ OMNIBRIDGE apparaît en bas à droite (déplaçable,
   réductible, position mémorisée).

Garanties de conception :

- **aucune frappe automatique**, **aucun envoi de message** dans la conversation : chaque
  action est un clic de l'utilisateur ;
- lecture DOM uniquement (texte visible), **jamais** les cookies, jetons de session ou
  stockage d'authentification du site ;
- le panneau appelle uniquement votre core local, avec le token Bearer ;
- si les sélecteurs d'un site changent, un repli prend le plus grand bloc de texte visible —
  et vous pouvez toujours sélectionner le texte à la main avant « Lire la réponse ».

Sans le panneau, la même lecture est disponible côté agent MCP :
`browser_get_last_assistant_message` (extension connectée), à combiner avec `webai_run`.

---

## 2. Pont presse-papier (sans extension, fonctionne partout)

```bash
omnibridge webai --prompt > prompt.txt          # prompt + catalogue (budget, catégories)
# → coller dans la conversation
omnibridge webai --run reponse.md               # exécute les appels JSON, rend le bloc de résultats
pbpaste | omnibridge webai --run -              # macOS : directement depuis le presse-papier
xclip -o | omnibridge webai --run -             # Linux
```

Le modèle répond par :

```json
{"calls": [{"tool": "project_inspect", "args": {"path": "."}},
           {"tool": "code_analyze", "args": {"path": "src/server/CombatServer.server.luau"}}]}
```

Le bloc renvoyé commence par `### OMNIBRIDGE RESULTS` et contient les sorties **réelles**,
y compris les refus de permission, les outils inconnus et les erreurs — que le modèle peut
alors corriger. Dashboard → **AI Connections** offre le même flux en trois boutons.

Options utiles : `--budget 4000` (prompt plus court), `--categories roblox,code`,
`--confirm` (autorise les outils de niveau 4 présents dans la réponse).

---

## 3. Actions OpenAPI (ChatGPT Custom GPT, Copilot Studio)

Chaque outil est publié comme une action typée : `POST /api/actions/<outil>`.

```bash
# Récupérer la spécification (publique, sans secret)
curl -s http://127.0.0.1:8765/openapi/actions.json -o omnibridge-actions.json

# Exposer le core (ChatGPT/Copilot appellent depuis le cloud, pas depuis votre machine)
cloudflared tunnel --url http://127.0.0.1:8765     # ou ngrok http 8765

# Déclarer l'URL publique pour que la spec pointe au bon endroit
export OMNIBRIDGE_PUBLIC_URL=https://votre-tunnel.trycloudflare.com
```

**ChatGPT (Custom GPT)** : *Explore GPTs → Create → Configure → Actions → Import from URL*
avec `https://…/openapi/actions.json`. Authentification : **API Key**, type **Bearer**,
valeur = `~/.omnibridge/token.txt`. Fonctionne sur les offres où les Custom GPTs existent
(inutile d'activer Developer Mode).

**Copilot Studio** : *Tools → New tool → REST API* (ou *Custom connector → OpenAPI*), import
du même fichier ; authentification « API key / Bearer ». Le même connecteur sert ensuite aux
agents Microsoft 365.

Vérification avant import :

```bash
omnibridge webai --check https://votre-tunnel.trycloudflare.com/mcp --token "$(cat ~/.omnibridge/token.txt)"
```

La commande exécute un vrai `initialize` MCP et signale précisément ce qui bloque
(http au lieu de https, localhost, 401, mauvais chemin). Pour les Actions, un simple
`curl https://…/openapi/actions.json` doit renvoyer du JSON valide.

---

## 4. API OpenAI-compatible (DeepSeek, Gemini, Grok/xAI, OpenAI, Groq, Mistral…)

Automatique, sans copier-coller : les 77 outils sont exportés en JSON Schema standard.

```bash
curl -s -H "Authorization: Bearer $(cat ~/.omnibridge/token.txt)" \
  http://127.0.0.1:8765/api/tools/openai | head -30
```

| Provider | `--provider` | Base URL | Variable de clé | Modèle par défaut |
| --- | --- | --- | --- | --- |
| DeepSeek | `deepseek` | `https://api.deepseek.com/v1` | `DEEPSEEK_API_KEY` | `deepseek-chat` |
| Gemini | `gemini` | `https://generativelanguage.googleapis.com/v1beta/openai` | `GEMINI_API_KEY` | `gemini-2.5-flash` |
| Grok (xAI) | `xai` | `https://api.x.ai/v1` | `XAI_API_KEY` | `grok-3` |
| OpenAI | `openai` | `https://api.openai.com/v1` | `OPENAI_API_KEY` | `gpt-4.1-mini` |
| Groq | `groq` | `https://api.groq.com/openai/v1` | `GROQ_API_KEY` | `llama-3.3-70b-versatile` |
| Mistral | `mistral` | `https://api.mistral.ai/v1` | `MISTRAL_API_KEY` | `mistral-large-latest` |
| OpenRouter | `openrouter` | `https://openrouter.ai/api/v1` | `OPENROUTER_API_KEY` | `deepseek/deepseek-chat` |
| Ollama (local) | `ollama` | `http://127.0.0.1:11434/v1` | — | `qwen2.5-coder:7b` |
| LM Studio | `lmstudio` | `http://127.0.0.1:1234/v1` | — | local |
| Autre | `custom` + `--base-url` | — | `OMNIBRIDGE_LLM_API_KEY` | `--model` |

```bash
export GEMINI_API_KEY=...
python examples/openai-compatible-agent.py --provider gemini "Analyse ce projet et corrige les TODO"

export XAI_API_KEY=...
python examples/openai-compatible-agent.py --provider xai "Ajoute un RemoteEvent de test et vérifie-le" --level 3

# sans clé
ollama serve && ollama pull qwen2.5-coder:7b
python examples/openai-compatible-agent.py --provider ollama --model qwen2.5-coder:7b "Analyse src/"
```

La clé reste dans votre environnement (jamais stockée), les niveaux de permission
s'appliquent, et les erreurs d'outil sont renvoyées au modèle pour qu'il se corrige.

---

## 5. ChatGPT Developer Mode (MCP distant)

Prérequis vérifiés (nov. 2026) : offre **payante**, Developer Mode activé
(*Settings → Connectors → Advanced*), URL **HTTPS publique** terminée par `/mcp`.

```bash
cloudflared tunnel --url http://127.0.0.1:8765
omnibridge webai --check https://votre-tunnel.trycloudflare.com/mcp --token "$(cat ~/.omnibridge/token.txt)"
# → chatgptReady: true
```

Puis *Plugins → Add → Create MCP App* : URL `https://…/mcp`, auth **Token** (Bearer).

---

## 6. Ce qui reste impossible — et pourquoi

| Idée | Statut | Raison |
| --- | --- | --- |
| Connexion MCP directe depuis DeepSeek/Gemini/Copilot/Grok web | ❌ | ces interfaces n'embarquent aucun client MCP |
| `localhost` appelé depuis ChatGPT/Gemini | ❌ | les appels viennent des serveurs du fournisseur |
| Pilotage automatique des UI de chat (remplir la zone de saisie, envoyer à votre place) | ❌ **refusé** | nécessite votre session authentifiée, viole les CGU, fragile et risqué pour votre compte |
| Lecture de cookies / jetons de session des sites | ❌ **refusé** | hors périmètre de sécurité d'OMNIBRIDGE |
| Exécution silencieuse d'appels sans votre action | ❌ **refusé** | le pont exige un clic ; l'audit enregistre tout |

Ces refus sont volontaires et documentés : ils protègent votre compte et gardent le modèle de
sécurité (niveaux 1–4, token, sandbox, audit) vérifiable.

---

## 7. Dépannage

| Symptôme | Cause / solution |
| --- | --- |
| Panneau absent | extension rechargée ? case « Panneau flottant » cochée ? page rechargée ? |
| Panneau : « Core non joignable » | `omnibridge --transport http` ; token dans le popup de l'extension |
| « Aucune réponse détectée » | le site a changé ses sélecteurs : sélectionnez le texte à la main puis « Lire la réponse » |
| `No tool call found` | la réponse ne contient pas de bloc JSON → collez le prompt d'abord |
| ChatGPT : « Action import failed » | URL non publique, ou JSON invalide (rechargez via `curl`) |
| ChatGPT/Copilot : 401 | auth Bearer : valeur exacte de `~/.omnibridge/token.txt` |
| `chatgptReady: false` | lire `problems[]` : http, localhost, 401, mauvais chemin |
| `Missing API key` (agent) | exportez la variable du provider (tableau §4) |
| Tunnel fermé | relancer le tunnel, mettre à jour l'URL du connecteur / de la spec |

---

## 8. Avertissement d'exposition publique (tunnel)

1. Gardez `OMNIBRIDGE_PERMISSION_LEVEL=2` (ou 1) tant que vous testez.
2. Le token Bearer est la seule barrière : supprimer `~/.omnibridge/token.txt` le révoque.
3. Restreignez le web : `OMNIBRIDGE_WEB_ALLOWED_HOSTS=create.roblox.com,luau.org`.
4. Fermez le tunnel après usage.
5. N'activez pas le niveau 4 sur un endpoint public : `confirm=true` peut être envoyé par le modèle.
