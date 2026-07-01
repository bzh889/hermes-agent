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
set "PYTHONIOENCODING=utf-8"
set "MTK_CA=%USERPROFILE%\.claude\skills\references\mtk-ca.crt"
set "SSL_CERT_FILE=%MTK_CA%"
set "REQUESTS_CA_BUNDLE=%MTK_CA%"
set "NODE_EXTRA_CA_CERTS=%MTK_CA%"
REM Resolve Electron to the manually-installed binary regardless of npm state.
set "ELECTRON_OVERRIDE_DIST_PATH=%~dp0apps\desktop\node_modules\electron\dist"
set "PYEXE=%~dp0venv\Scripts\python.exe"

if not exist "%PYEXE%" (
    echo [!] venv not found at "%PYEXE%" - rebuild it. See setup-hermes-mtk.sh / README.
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
