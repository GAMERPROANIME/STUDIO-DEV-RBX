@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>nul
title OMNIBRIDGE - Panneau DeepSeek
cd /d "%~dp0"

echo ============================================================
echo    OMNIBRIDGE AI   -   Panneau DeepSeek / Roblox Studio
echo ============================================================
echo.

if exist ".venv\Scripts\python.exe" goto ready

echo [1/2] Premiere installation (2 a 3 minutes, une seule fois).
echo       Il faut Internet et Python 3.11 ou plus recent.
echo.

where py >nul 2>nul
if not errorlevel 1 (
    py -3 -c "import sys; raise SystemExit(0 if sys.version_info>=(3,11) else 1)" >nul 2>nul
    if not errorlevel 1 (
        py -3 -m venv .venv
        goto install
    )
)
where python >nul 2>nul
if errorlevel 1 goto nopython
python -c "import sys; raise SystemExit(0 if sys.version_info>=(3,11) else 1)" >nul 2>nul
if errorlevel 1 goto nopython
python -m venv .venv

:install
if not exist ".venv\Scripts\python.exe" goto error
".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
".venv\Scripts\python.exe" -m pip install -e . --quiet
if errorlevel 1 goto error
echo       Installation terminee.
echo.

:ready
echo [2/2] Demarrage du serveur local...
echo.
set "TOKEN="
for /f "usebackq delims=" %%T in (`".venv\Scripts\python.exe" -m omnibridge --print-token`) do set "TOKEN=%%T"
echo   +------------------------------------------------------------+
echo   ^|  CODE A COLLER DANS L'EXTENSION :                          ^|
echo   ^|  !TOKEN!  ^|
echo   +------------------------------------------------------------+
echo.
echo   La page d'installation va s'ouvrir dans ton navigateur.
echo   Garde cette fenetre OUVERTE pendant que tu travailles.
echo   Pour tout arreter : ferme cette fenetre.
echo.
start "" cmd /c "timeout /t 3 >nul & explorer http://127.0.0.1:8765/demarrer"
".venv\Scripts\python.exe" -m omnibridge --transport http --host 127.0.0.1 --port 8765 --level 3
echo.
echo Serveur arrete. Tu peux fermer cette fenetre.
pause
exit /b 0

:nopython
echo.
echo   PROBLEME : Python est introuvable (ou trop ancien).
echo     1. Telecharge Python 3.11 ou plus recent : https://www.python.org/downloads/
echo     2. Pendant l'installation, coche "Add python.exe to PATH".
echo     3. Relance ce fichier.
echo.
pause
exit /b 1

:error
echo.
echo   PROBLEME : l'installation a echoue. Verifie ta connexion Internet puis relance.
echo.
pause
exit /b 1
