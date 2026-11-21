# DeepSeek web → Roblox Studio, pas à pas (sans être ingénieur)

**Ce que tu vas obtenir :** sur `chat.deepseek.com`, un panneau OMNIBRIDGE en bas à droite avec
trois voyants et deux boutons.

1. **Connecter** → vérifie la page, le serveur local et Roblox Studio (vert = prêt)
2. Tu écris ta demande, tu cliques **Démarrer la boucle**
3. Le panneau écrit dans le chat, attend la réponse de DeepSeek, **exécute les outils dans
   Studio**, renvoie les vrais résultats, et recommence jusqu'à la réponse finale.
4. **Arrêter** interrompt tout à tout moment. Le **mode manuel** (4 boutons) reste disponible,
   replié dans le panneau, si tu préfères cliquer toi-même.

> **Honnêteté** : la logique de la boucle et des adaptateurs est testée automatiquement
> (`tests/test_provider_loop.py` exécute le vrai code dans Node). En revanche, personne n'a pu
> cliquer à ta place sur le vrai chat DeepSeek depuis un environnement sans navigateur : le
> **premier essai réel, c'est toi qui le fais**. Si un bouton ne réagit pas, dis-moi la ligne
> affichée dans le journal du panneau.

---

## Étape 1 — Télécharger et décompresser

👉 **ZIP à télécharger :**
https://codeload.github.com/GAMERPROANIME/STUDIO-DEV-RBX/zip/refs/heads/arena/06334a9a-studio-dev-rbx

Clic droit sur le ZIP → **Extraire tout…** → choisis `Documents` par exemple.
Tu obtiens un dossier `STUDIO-DEV-RBX-arena-06334a9a-studio-dev-rbx` — **retiens son chemin**,
on en aura besoin deux fois (étape 3 pour le lancer, étape 4 pour l'extension).

---

## Étape 2 — Installer Python (une seule fois)

1. https://www.python.org/downloads/ → gros bouton **Download Python**
2. Lance l'installateur → **coche « Add python.exe to PATH »** (en bas de la 1ʳᵉ fenêtre)
3. **Install Now** → **Close**

*Déjà installé ? Passe à l'étape 3.*

---

## Étape 3 — Lancer le serveur (double-clic)

| Ton ordinateur | Fichier |
| --- | --- |
| **Windows** | `DEMARRER-PANNEAU-WINDOWS.bat` |
| **Mac** | `DEMARRER-PANNEAU-MAC-LINUX.command` (clic droit → **Ouvrir** si macOS bloque) |
| **Linux** | `DEMARRER-PANNEAU-MAC-LINUX.command` |

Ce qui se passe :

1. Une fenêtre noire s'ouvre. La première fois, elle installe tout (2 à 3 min, Internet requis).
2. Elle affiche un **CODE** (64 caractères) **et ouvre la page d'installation** :
   `http://127.0.0.1:8765/demarrer`
3. **Ne ferme pas cette fenêtre** tant que tu utilises DeepSeek.

> Si la page ne s'ouvre pas : tape `http://127.0.0.1:8765/demarrer` dans la barre d'adresse.

---

## Étape 4 — Installer l'extension (5 clics, une seule fois)

1. Dans Chrome (ou Edge), tape dans la barre d'adresse : `chrome://extensions`
2. En haut à droite : active **Mode développeur**
3. En haut à gauche : clique **Charger l'extension non empaquetée**
4. Dans la fenêtre qui s'ouvre, va dans le dossier OMNIBRIDGE décompressé, puis **ouvre le
   sous-dossier `extension`** (attention : c'est `extension`, pas le dossier parent)
5. Épingle l'icône **OMNIBRIDGE** (icône puzzle 🧩 en haut à droite → épingle)

**Firefox** : `about:debugging` → *Ce Firefox* → *Charger un module temporaire* → choisis le
fichier `extension/manifest.firefox.json`.

---

## Étape 5 — Brancher l'extension sur le serveur (30 secondes)

1. Clique sur l'icône **OMNIBRIDGE** (celle que tu viens d'épingler)
2. **Serveur local** : `http://127.0.0.1:8765` (normalement déjà rempli)
3. **Token** : clique sur le bouton **Copier le code** de la page `…/demarrer`, puis colle-le ici
4. Clique **« Connecter au core Python »** → le voyant doit passer au **vert**
5. Vérifie que la case **« Panneau flottant sur ChatGPT / DeepSeek / … »** est cochée

---

## Étape 6 — Activer Roblox Studio

1. Ouvre **Roblox Studio** et une place (un jeu).
2. **Assistant → Réglages → MCP Servers → active « Enable Studio as MCP server »**
3. Reviens sur la page `http://127.0.0.1:8765/demarrer` et clique **Tester la connexion**.
   Tu dois voir : « Prêt : DeepSeek peut piloter Studio ».

---

## Étape 7 — Utiliser DeepSeek (mode automatique)

1. Va sur https://chat.deepseek.com/ et ouvre une conversation.
2. En bas à droite, le panneau **OMNIBRIDGE** apparaît (tu peux le déplacer en le glissant).
3. Clique **Connecter**. Trois lignes s'affichent :

   | Voyant | Vert signifie |
   | --- | --- |
   | Page IA | zone de saisie trouvée + bouton d'envoi |
   | Serveur local | le serveur répond (77 outils, niveau 3) |
   | Roblox Studio | le serveur MCP de Studio répond (tu as « MCP Ready » dans Studio) |

4. Écris ta demande dans **« Ce que je veux faire »**, par exemple :
   - « Crée une part rouge de 4×1×4 au-dessus de la base, nommée `SpawnPlatform`. »
   - « Lis le script `ServerScriptService.CAR` et résume ce qu'il fait. »
   - « Liste les objets présents dans Workspace. »
5. Clique **Démarrer la boucle**. Le journal affiche : cycle 1 → réponse → outils exécutés →
   cycle 2 → réponse finale.
6. **Arrêter** si tu veux reprendre la main.

Garde-fous : 10 cycles maximum, arrêt automatique sur la réponse finale, anti-doublon (si les
mêmes appels reviennent), deux échecs consécutifs = arrêt, et **rien ne démarre sans ton clic**.

### Mode manuel (si tu préfères tout contrôler)

Replie la section **« Mode manuel (4 boutons) »** dans le panneau :
**Prompt** (copie le protocole) → colle dans le chat → **Lire la réponse** → **Exécuter** →
**Copier** → recolle les résultats. C'est la version clic par clic de la même boucle.

---

## Les 4 boutons, expliqués

| Bouton | Ce qu'il fait | Ce qu'il ne fait pas |
| --- | --- | --- |
| **Prompt** | copie la liste des outils réels + le mode d'emploi | n'envoie rien à ta place |
| **Lire la réponse** | lit le dernier message de l'IA dans la page | ne lit pas tes cookies, ni tes conversations |
| **Exécuter** | lance vraiment les outils demandés | n'exécute que des blocs JSON valides et des outils connus |
| **Copier** | copie les résultats réels | ne modifie rien |

OMNIBRIDGE **ne tape jamais** dans la zone de texte de DeepSeek et **n'envoie jamais** de message
tout seul : c'est toi qui cliques. Aucun cookie, aucun mot de passe n'est lu.

---

## Si quelque chose ne va pas

| Ce que tu vois | Ce qu'il faut faire |
| --- | --- |
| Le panneau n'apparaît pas sur DeepSeek | Icône OMNIBRIDGE → la case « Panneau flottant » doit être cochée ; recharge l'onglet DeepSeek (F5) |
| J'ai mis à jour le dossier, rien ne change | `chrome://extensions` → icône **↻** sur OMNIBRIDGE, puis F5 sur DeepSeek |
| « Zone de saisie introuvable » | Clique dans la zone de texte de DeepSeek, puis re-clique **Connecter** |
| La boucle écrit mais rien ne part | DeepSeek a changé son interface : envoie-moi la ligne du journal, l'adaptateur est à ajuster |
| « token » refusé / voyant rouge | Recopie le code depuis `…/demarrer` (bouton **Copier**), sans espace ; clique de nouveau **Connecter** |
| « Studio MCP command not found » | Studio doit être **ouvert** avec le serveur MCP activé (étape 6) ; sinon mets Studio à jour |
| Rien ne s'exécute après **Exécuter** | La réponse doit contenir un bloc `{"calls":[…]}` : dis à DeepSeek « exécute maintenant avec OMNIBRIDGE » |
| « permission denied » | Ferme la fenêtre noire et relance `DEMARRER-PANNEAU-…` (le niveau 3 est activé automatiquement) |
| La fenêtre noire se ferme toute seule | Relance le fichier et **lis les 3 dernières lignes** ; Python manque souvent (étape 2) |
| J'ai lancé `DEMARRER-WINDOWS.bat` au lieu de `DEMARRER-PANNEAU-…` | Celui-ci démarre le **futur pont automatique** (port 17613), pas le panneau. Ferme-le et lance `DEMARRER-PANNEAU-WINDOWS.bat` |
| Le port 8765 est déjà utilisé | Une autre fenêtre OMNIBRIDGE est déjà ouverte : utilise celle-là |

---

## Limites, dites franchement

- **Mode automatique livré** : la boucle écrit, attend, exécute et renvoie les résultats. Ce qui
  reste fragile, c'est le **DOM des plateformes** : si DeepSeek change son interface, l'adaptateur
  (`extension/site-adapters.js`) doit être ajusté. Le mode manuel reste le filet de sécurité.
- La boucle lit le **texte affiché** de la réponse, pas les données internes de DeepSeek.
- Pas encore branché : la connexion directe au **pont `17613`** (sans passer par le serveur 8765).
  Aujourd'hui la boucle utilise le serveur local (77 outils + Studio).
- Niveau de permission **3** : lire + modifier (créer/déplacer des objets, éditer des scripts).
  Les actions classées niveau 4 demandent une confirmation explicite et ne passent pas par le panneau.
- Une IA **web** n'a pas accès à MCP : tout passe par ton navigateur et ton ordinateur. Rien n'est
  envoyé à un serveur OMNIBRIDGE (il n'y en a pas).

---

## Pour aller plus loin

- Pont automatique (en cours) : [`docs/STUDIO_BRIDGE.md`](docs/STUDIO_BRIDGE.md)
- Autres plateformes (ChatGPT, Gemini, Copilot, Grok) : [`docs/WEB_AI.md`](docs/WEB_AI.md)
- Extension en détail : [`docs/EXTENSION.md`](docs/EXTENSION.md)
- Serveur + outillage : [`DEMARRAGE_SIMPLE.md`](DEMARRAGE_SIMPLE.md)
