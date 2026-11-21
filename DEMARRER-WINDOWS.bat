@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>nul
title OMNIBRIDGE - Pont Roblox Studio
cd /d "%~dp0"

echo ============================================================
echo    OMNIBRIDGE AI   -   Pont Roblox Studio
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
echo [2/2] Demarrage du pont...
echo.
set "TOKEN="
for /f "usebackq delims=" %%T in (`".venv\Scripts\python.exe" -m python_bridge --print-token`) do set "TOKEN=%%T"
echo   +------------------------------------------------------------+
echo   ^|  CODE D'APPAIRAGE :                                        ^|
echo   ^|  !TOKEN!  ^|
echo   +------------------------------------------------------------+
echo.
echo   Une page va s'ouvrir : http://127.0.0.1:17613
echo   Garde cette fenetre OUVERTE pendant que tu travailles.
echo   Pour arreter le pont : ferme cette fenetre.
echo.
start "" cmd /c "timeout /t 3 >nul & explorer http://127.0.0.1:17613/"
".venv\Scripts\python.exe" -m python_bridge
echo.
echo Le pont est arrete. Tu peux fermer cette fenetre.
pause
exit /b 0

:nopython
echo.
echo   PROBLEME : Python est introuvable (ou trop ancien).
echo     1. Telecharge Python 3.11 ou plus recent :
echo        https://www.python.org/downloads/
echo     2. Pendant l'installation, coche "Add python.exe to PATH".
echo     3. Relance ce fichier en double-cliquant.
echo.
pause
exit /b 1

:error
echo.
echo   PROBLEME : l'installation a echoue.
echo     Verifie ta connexion Internet, puis relance ce fichier.
echo.
pause
exit /b 1
