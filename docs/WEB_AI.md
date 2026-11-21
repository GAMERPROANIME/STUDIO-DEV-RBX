# Utiliser OMNIBRIDGE depuis ChatGPT, DeepSeek, Gemini…

## Réponse courte

| Plateforme | MCP natif ? | Ce qui marche réellement |
| --- | --- | --- |
| Claude Desktop / Claude Code | ✅ | MCP stdio ou HTTP — automatique (`docs/CONNECT.md`) |
| Cursor / VS Code / Continue | ✅ | MCP stdio — automatique |
| **ChatGPT web** | ✅ mais payant + distant | MCP **HTTPS public** via tunnel (Developer Mode), sinon pont presse-papier |
| **DeepSeek web** | ❌ | pont presse-papier |
| **Gemini / Copilot / Mistral / Grok web** | ❌ | pont presse-papier |
| **API DeepSeek / OpenAI / Groq** | ✅ function calling | agent automatique (script fourni) |
| **Ollama / LM Studio** | ✅ function calling local | agent automatique, sans clé |

Deux familles de solutions, toutes deux implémentées dans le core Python :

1. **Automatique** — quand le modèle expose une API *ou* un client MCP : il appelle les 76
   outils directement.
2. **Pont presse-papier** — quand l'interlocuteur est une interface web sans MCP : le modèle
   décrit ses appels en JSON, vous les collez dans OMNIBRIDGE, il exécute et vous rendez les
   résultats. Cela fonctionne partout, sans clé, sans tunnel.

> Ce qu'OMNIBRIDGE **ne fait pas** (volontairement) : piloter l'interface web de ChatGPT ou
> DeepSeek avec des cookies de session, contourner leurs restrictions, ou réutiliser vos
> identifiants. Ces pratiques violent les conditions d'utilisation et exposent vos comptes.

---

## 1. Pont presse-papier (ChatGPT web, DeepSeek web, Gemini, Copilot…)

```bash
omnibridge webai --prompt > prompt.txt        # 1. prompt système, catalogue inclus
omnibridge webai --prompt --budget 4000 --categories roblox,code > prompt.txt
```

2. Collez le contenu dans la conversation (premier message, ou « instructions
   personnalisées » de ChatGPT / « system prompt » de DeepSeek).
3. Le modèle répond par un bloc :

```json
{"calls": [{"tool": "project_inspect", "args": {"path": "."}},
           {"tool": "code_analyze", "args": {"path": "src/server/CombatServer.server.luau"}}]}
```

4. Copiez cette réponse dans un fichier et exécutez-la :

```bash
omnibridge webai --run reponse.md            # affiche un bloc « ### OMNIBRIDGE RESULTS »
pbpaste | omnibridge webai --run -           # macOS, directement depuis le presse-papier
xclip -o | omnibridge webai --run -          # Linux
```

5. Recollez le bloc de résultats dans la conversation : le modèle continue avec des données
   **réelles**. Répétez jusqu'à la réponse finale.

Dans le dashboard (**AI Connections**), le même flux est disponible : *Générer le prompt* →
copier → *Réponse du modèle* → *Exécuter les appels* → *Copier le bloc résultat*.

Garanties :
- les appels sont validés contre le catalogue réel : un outil inventé est refusé et signalé
  au modèle dans le bloc de résultats ;
- les niveaux de permission s'appliquent, un outil de niveau 4 exige `confirm: true` et la
  case « Autoriser les appels niveau 4 » (ou `--confirm`) ;
- tout est audité (`system_audit_log`).

Astuce complémentaire : si la conversation DeepSeek/ChatGPT est ouverte dans votre navigateur,
un agent connecté en MCP peut la relire avec `browser_get_page_content` (extension OMNIBRIDGE),
ce qui évite même le copier-coller dans un sens.

---

## 2. API OpenAI-compatible (DeepSeek, OpenAI, Groq, Ollama, LM Studio) — automatique

Les 76 outils sont exportés en JSON Schema standard :

```bash
curl -s -H "Authorization: Bearer $(cat ~/.omnibridge/token.txt)" \
  http://127.0.0.1:8765/api/tools/openai | head -40

omnibridge webai --openai-tools > tools.json   # même contenu, hors ligne
```

Boucle agent fournie (`omnibridge/openai_agent.py`) :

```bash
export DEEPSEEK_API_KEY=sk-...                 # ou OPENAI_API_KEY / GROQ_API_KEY
python examples/openai-compatible-agent.py "Inspecte le projet et liste les TODO"

# Ollama local, aucune clé
ollama serve && ollama pull qwen2.5-coder:7b
python examples/openai-compatible-agent.py --provider ollama \
  --model qwen2.5-coder:7b --level 3 "Ajoute un RemoteEvent de test et vérifie-le"
```

| Provider | Base URL | Variable de clé | Modèle par défaut |
| --- | --- | --- | --- |
| `deepseek` | `https://api.deepseek.com/v1` | `DEEPSEEK_API_KEY` | `deepseek-chat` |
| `openai` | `https://api.openai.com/v1` | `OPENAI_API_KEY` | `gpt-4.1-mini` |
| `groq` | `https://api.groq.com/openai/v1` | `GROQ_API_KEY` | `llama-3.3-70b-versatile` |
| `ollama` | `http://127.0.0.1:11434/v1` | — | `qwen2.5-coder:7b` |
| `lmstudio` | `http://127.0.0.1:1234/v1` | — | local |

La clé n'est jamais stockée par OMNIBRIDGE : elle est lue dans l'environnement. Les erreurs
d'outil (permission, sandbox, fichier absent) sont renvoyées au modèle, qui peut se corriger —
c'est la boucle plan → exécution → test → correction, côté modèle.

---

## 3. ChatGPT Developer Mode (MCP distant)

Prérequis réels (vérifiés en novembre 2026) :

- offre **payante** (Plus, Pro, Business, Enterprise, Edu) : la Free n'a pas les connecteurs
  personnalisés ;
- Developer Mode activé : *Settings → Connectors → Advanced* (parfois *Security and login*) ;
- une URL **HTTPS publique** terminée par `/mcp` : ChatGPT ne joint jamais `localhost`.

Exposer le core avec un tunnel :

```bash
# Cloudflare (aucun compte pour un Quick Tunnel)
cloudflared tunnel --url http://127.0.0.1:8765

# ou ngrok
ngrok http 8765

# ou le tunnel officiel OpenAI (Secure MCP Tunnel) si vous l'utilisez déjà
```

Puis vérifier **avant** de coller l'URL dans ChatGPT :

```bash
omnibridge webai --check https://votre-tunnel.trycloudflare.com/mcp --token "$(cat ~/.omnibridge/token.txt)"
```

La commande exécute un vrai `initialize` Streamable HTTP et répond `chatgptReady: true/false`
avec la liste précise des problèmes (http au lieu de https, localhost, 401, mauvais endpoint…).
Dans le dashboard : **AI Connections → ChatGPT Developer Mode → Vérifier l'endpoint**.

Ensuite : *Plugins → Add → Create MCP App*, URL `https://…/mcp`, authentification **Token**
(Bearer = `~/.omnibridge/token.txt`).

### Avertissement de sécurité pour l'exposition publique

Un tunnel rend le serveur joignable depuis Internet :

1. Gardez `OMNIBRIDGE_PERMISSION_LEVEL=2` (ou 1) tant que vous testez.
2. Le token Bearer est la seule barrière : ne le partagez pas, révoquez en supprimant
   `~/.omnibridge/token.txt` (un nouveau sera généré).
3. Restreignez les domaines web : `OMNIBRIDGE_WEB_ALLOWED_HOSTS=create.roblox.com,luau.org`.
4. Fermez le tunnel après usage (`Ctrl+C`).
5. Les outils de niveau 4 (`process_run`, `file_delete`) restent protégés par `confirm=true`,
   mais ChatGPT peut l'envoyer : ne laissez pas le niveau 4 actif sur un endpoint public.

---

## 4. Dépannage

| Symptôme | Cause / solution |
| --- | --- |
| ChatGPT refuse l'URL | http:// ou localhost → il faut un tunnel HTTPS public |
| `401` sur `/mcp` | token manquant dans le connecteur (auth « Token », pas OAuth) |
| Le modèle web invente des résultats | il n'a pas reçu le prompt : recommencez à l'étape 1, exigez le bloc `### OMNIBRIDGE RESULTS` |
| `No tool call found` | la réponse ne contient pas de bloc JSON → demandez `{"calls": [...]}` |
| Outil inconnu dans le bloc | fautes de frappe/nom inventé : le bloc de résultats le signale au modèle |
| `Missing API key` | exportez la variable du provider (voir tableau) |
| Ollama renvoie 404 | base URL `http://127.0.0.1:11434/v1` et modèle téléchargé (`ollama pull`) |
| Tunnel fermé, ChatGPT se déconnecte | relancer le tunnel et mettre à jour l'URL du connecteur |
