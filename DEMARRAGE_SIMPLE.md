# Démarrer OMNIBRIDGE — version simple (sans être ingénieur)

Tu as **5 minutes** et **aucune ligne de code** à taper. Tout se fait en double-cliquant.

---

## 1. Télécharger le dossier

**Lien direct (téléchargement du ZIP) :**

👉 https://codeload.github.com/GAMERPROANIME/STUDIO-DEV-RBX/zip/refs/heads/arena/06334a9a-studio-dev-rbx

Clique sur le lien, le fichier `STUDIO-DEV-RBX-arena-06334a9a-studio-dev-rbx.zip` se télécharge.
Ensuite : **clic droit sur le ZIP → « Extraire tout… »** (Windows) ou **double-clic** (Mac), et
place le dossier dans `Documents` par exemple.

> Si tu préfères voir les fichiers avant de télécharger :
> https://github.com/GAMERPROANIME/STUDIO-DEV-RBX/tree/arena/06334a9a-studio-dev-rbx
> (bouton vert **Code** → **Download ZIP**)

---

## 2. Installer Python (une seule fois dans ta vie)

Le pont est écrit en Python. C'est le seul logiciel à installer.

1. Va sur https://www.python.org/downloads/ et clique sur le gros bouton **Download Python**
2. Lance l'installateur et **coche la case « Add python.exe to PATH »** en bas de la première
   fenêtre (c'est le seul piège de toute la procédure)
3. Clique **Install Now**, puis **Close**

*Déjà installé ? Passe à l'étape 3.*

---

## 3. Lancer le pont (double-clic)

| Ton ordinateur | Fichier à double-cliquer |
| --- | --- |
| **Windows** | `DEMARRER-WINDOWS.bat` |
| **Mac** | `DEMARRER-MAC-LINUX.command` (si macOS bloque : clic droit → **Ouvrir** → **Ouvrir**) |
| **Linux** | `DEMARRER-MAC-LINUX.command` (ou `bash DEMARRER-MAC-LINUX.command`) |

Ce qui se passe :

1. Une fenêtre noire s'ouvre. **La première fois**, elle installe tout (2 à 3 minutes, il faut
   Internet). C'est normal, elle affiche des lignes qui défilent.
2. Elle affiche ensuite un **CODE D'APPAIRAGE** (64 caractères) et ouvre une page dans ton
   navigateur : `http://127.0.0.1:17613`
3. **Garde la fenêtre noire ouverte** pendant que tu travailles. Pour tout arrêter : ferme-la.

**Rien d'autre à faire.** Pas de commande à taper.

---

## 4. La page qui s'ouvre (tout est dedans)

La page locale s'appelle **Pont OMNIBRIDGE**. Elle te dit, en français :

- **un voyant d'état** :
  - 🟢 vert = Studio est connecté et ses outils sont disponibles
  - 🟠 orange = ça répond, mais une chose manque (place fermée, MCP désactivé…)
  - 🔴 rouge = Studio n'est pas trouvé ou ne répond pas
- **ce qu'il faut faire**, en une phrase (par exemple : « dans Studio : Assistant → Réglages →
  MCP Servers → active *Enable Studio as MCP server* »)
- **ton code d'appairage**, avec un bouton **Copier**
- la **liste des outils** réellement fournis par Roblox Studio (si la liste est vide, elle reste
  vide : OMNIBRIDGE n'invente jamais d'outil)
- un bouton **Re-vérifier l'état** après chaque manipulation

---

## 5. Activer Roblox Studio (3 clics)

1. Ouvre **Roblox Studio** et une place (un jeu).
2. **Assistant → Réglages → MCP Servers → active « Enable Studio as MCP server »**.
3. Reviens sur la page `http://127.0.0.1:17613` et clique **Re-vérifier l'état**.
   Le voyant doit passer au **vert**.

---

## Ce qui fonctionne aujourd'hui (et ce qui arrive ensuite)

**Fonctionne et est testé (vérifiable chez toi) :**

- le pont local (WebSocket `ws://127.0.0.1:17613`), protégé par code d'appairage
- la connexion au **serveur MCP officiel de Roblox Studio**, la découverte dynamique de ses outils
- la page de réglage ci-dessus, l'état en français, le journal d'audit
- 133 tests automatiques, dont un test de bout en bout du pont

**Pas encore là — et je ne vais pas prétendre le contraire :**

- l'extension navigateur qui relie automatiquement ChatGPT / DeepSeek / Gemini / Kimi / GLM /
  Qwen / Arena / Meta AI à ce pont (prochaine étape, en cours de développement)
- donc : **aucune IA web ne pilote encore Studio via cette chaîne**. Le pont, lui, est réel et
  vérifiable dès maintenant.

---

## Problèmes courants

| Ce que tu vois | Ce qu'il faut faire |
| --- | --- |
| `Python est introuvable` dans la fenêtre noire | Installe Python (étape 2) en cochant **Add python.exe to PATH**, puis redémarre le fichier `.bat` |
| La fenêtre noire se ferme aussitôt | Relance le fichier et **lis les 3 dernières lignes** : elles disent quoi corriger |
| « Windows a protégé votre PC » | **Informations complémentaires** → **Exécuter quand même** (le fichier est un simple `.bat` lisible dans le dossier) |
| `l'installation a echoue` | Vérifie ta connexion Internet, puis relance |
| Voyant 🔴 « Studio introuvable » | Ouvre Roblox Studio et active le serveur MCP (étape 5) ; sinon mets Studio à jour |
| Voyant 🟠 « MCP désactivé » | Assistant → Réglages → MCP Servers → active le serveur, puis **Re-vérifier** |
| La page ne s'ouvre pas | Tape toi-même `http://127.0.0.1:17613` dans la barre d'adresse |
| `address already in use` | Le pont tourne déjà : cherche la fenêtre noire ouverte, ou redémarre l'ordinateur |

---

## Pour aller plus loin

- Détails techniques complets : [`docs/STUDIO_BRIDGE.md`](docs/STUDIO_BRIDGE.md)
- Vérifier le pont sans navigateur : `python examples/studio_bridge_client.py --list`
- Autres façons de connecter une IA : [`docs/WEB_AI.md`](docs/WEB_AI.md)
