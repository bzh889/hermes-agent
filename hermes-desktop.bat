@echo off
REM ============================================================================
REM  Hermes Agent - MTK desktop app launcher (Electron, no WSL)
REM  Double-click -> launches the native Hermes Desktop window.
REM
REM  Uses --source --skip-build on purpose: it launches the pre-built renderer
REM  (apps/desktop/dist) + the already-installed Electron binary WITHOUT running
REM  npm ci. A bare `hermes gui` would re-run npm install, which on this network
REM  re-downloads Electron from GitHub (blocked) and wipes the working binary —
REM  so always launch via this script.
REM ============================================================================
cd /d "%~dp0"

set "HERMES_HOME=%USERPROFILE%\.hermes"
set "HERMES_DESKTOP_HERMES_ROOT=%~dp0"
set "PYTHONIOENCODING=utf-8"
set "MTK_CA=%USERPROFILE%\.claude\skills\references\mtk-ca.crt"
set "SSL_CERT_FILE=%MTK_CA%"
set "REQUESTS_CA_BUNDLE=%MTK_CA%"
set "NODE_EXTRA_CA_CERTS=%MTK_CA%"
set "HERMES_PACKAGED=%~dp0apps\desktop\release\win-unpacked\Hermes.exe"
if exist "%HERMES_PACKAGED%" (
    echo Launching packaged Hermes Desktop ...
    start "" "%HERMES_PACKAGED%" %*
    exit /b 0
)

REM Resolve Electron from either a workspace-local or npm-hoisted install.
set "ELECTRON_LOCAL=%~dp0apps\desktop\node_modules\electron\dist\electron.exe"
set "ELECTRON_HOISTED=%~dp0node_modules\electron\dist\electron.exe"
if exist "%ELECTRON_LOCAL%" set "ELECTRON_OVERRIDE_DIST_PATH=%~dp0apps\desktop\node_modules\electron\dist"
if not exist "%ELECTRON_LOCAL%" if exist "%ELECTRON_HOISTED%" set "ELECTRON_OVERRIDE_DIST_PATH=%~dp0node_modules\electron\dist"

set "PYEXE=%~dp0.venv\Scripts\python.exe"
if not exist "%PYEXE%" set "PYEXE=%~dp0venv\Scripts\python.exe"

if not exist "%PYEXE%" (
    echo [!] venv not found at "%PYEXE%" - rebuild it. See setup-hermes-mtk.sh / README.
    pause
    exit /b 1
)
if not exist "%ELECTRON_LOCAL%" if not exist "%ELECTRON_HOISTED%" (
    echo [!] Electron runtime not found in the desktop workspace or root node_modules.
    pause
    exit /b 1
)
if not exist "%~dp0apps\desktop\dist\index.html" (
    echo [!] Desktop renderer not built. Build once with:
    echo       npm run build -w apps/desktop     ^(or: node node_modules\vite\bin\vite.js build  in apps\desktop^)
    pause
    exit /b 1
)

echo Launching Hermes Desktop ...
"%PYEXE%" -m hermes_cli.main gui --source --skip-build %*
pause
