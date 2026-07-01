@echo off
REM ============================================================================
REM  Hermes Agent - MTK web dashboard launcher (browser GUI, no WSL)
REM  Double-click -> starts the Python dashboard and opens the chat UI in your
REM  browser at http://127.0.0.1:9119 . Close this window to stop the server.
REM ============================================================================
cd /d "%~dp0"

set "HERMES_HOME=%USERPROFILE%\.hermes"
set "PYTHONIOENCODING=utf-8"
set "MTK_CA=%USERPROFILE%\.claude\skills\references\mtk-ca.crt"
set "SSL_CERT_FILE=%MTK_CA%"
set "REQUESTS_CA_BUNDLE=%MTK_CA%"
set "NODE_EXTRA_CA_CERTS=%MTK_CA%"
set "PYEXE=%~dp0venv\Scripts\python.exe"

if not exist "%PYEXE%" (
    echo [!] venv not found at "%PYEXE%" - rebuild it. See setup-hermes-mtk.sh / README.
    pause
    exit /b 1
)

echo Starting Hermes web dashboard at http://127.0.0.1:9119  (Ctrl+C to stop) ...
"%PYEXE%" -m hermes_cli.main dashboard %*
pause
