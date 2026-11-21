#!/bin/bash
# OMNIBRIDGE - Panneau DeepSeek / Roblox Studio (macOS / Linux)
# Double-clic sur macOS, ou : bash DEMARRER-PANNEAU-MAC-LINUX.command
set -u
cd "$(dirname "$0")" || exit 1

echo "============================================================"
echo "   OMNIBRIDGE AI   -   Panneau DeepSeek / Roblox Studio"
echo "============================================================"
echo

if [ ! -x ".venv/bin/python" ]; then
    echo "[1/2] Premiere installation (2 a 3 minutes, une seule fois)."
    PY=""
    for candidate in python3.13 python3.12 python3.11 python3; do
        if command -v "$candidate" >/dev/null 2>&1 &&
           "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info>=(3,11) else 1)' 2>/dev/null; then
            PY="$candidate"; break
        fi
    done
    if [ -z "$PY" ]; then
        echo
        echo "  PROBLEME : Python 3.11+ est introuvable."
        echo "    macOS  : https://www.python.org/downloads/  (ou: brew install python)"
        echo "    Ubuntu : sudo apt install python3 python3-venv"
        echo
        read -r -p "Appuie sur Entree pour fermer..." _
        exit 1
    fi
    "$PY" -m venv .venv || { echo "  PROBLEME : creation de l'environnement impossible."; exit 1; }
    .venv/bin/python -m pip install --upgrade pip --quiet
    .venv/bin/python -m pip install -e . --quiet || {
        echo "  PROBLEME : installation echouee (connexion Internet ?)"; exit 1; }
    echo "      Installation terminee."
    echo
fi

echo "[2/2] Demarrage du serveur local..."
echo
TOKEN="$(.venv/bin/python -m omnibridge --print-token)"
echo "  +------------------------------------------------------------+"
echo "  |  CODE A COLLER DANS L'EXTENSION :                          |"
echo "  |  $TOKEN"
echo "  +------------------------------------------------------------+"
echo
echo "  La page d'installation va s'ouvrir : http://127.0.0.1:8765/demarrer"
echo "  Garde cette fenetre OUVERTE. Pour tout arreter : Ctrl+C."
echo

( sleep 3
  if command -v open >/dev/null 2>&1; then open "http://127.0.0.1:8765/demarrer" >/dev/null 2>&1
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "http://127.0.0.1:8765/demarrer" >/dev/null 2>&1
  fi ) &

exec .venv/bin/python -m omnibridge --transport http --host 127.0.0.1 --port 8765 --level 3
