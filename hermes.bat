@echo off
REM ============================================================================
REM  Hermes Agent - MTK one-click launcher (Windows, no WSL)
REM  Double-click to start an interactive chat, or run from a terminal with
REM  args, e.g.  hermes.bat model    hermes.bat doctor    hermes.bat -z "hi"
REM ============================================================================
setlocal
cd /d "%~dp0"

REM --- MTK environment (double-click does NOT inherit ~/.bashrc, so set here) ---
set "HERMES_HOME=%USERPROFILE%\.hermes"
set "PYTHONIOENCODING=utf-8"
set "MTK_CA=%USERPROFILE%\.claude\skills\references\mtk-ca.crt"
set "SSL_CERT_FILE=%MTK_CA%"
set "REQUESTS_CA_BUNDLE=%MTK_CA%"
set "NODE_EXTRA_CA_CERTS=%MTK_CA%"

set "PYEXE=%~dp0venv\Scripts\python.exe"
if not exist "%PYEXE%" (
    echo [!] venv not found at "%PYEXE%".
    echo     Rebuild it, then retry. See setup-hermes-mtk.sh / README.
    pause
    exit /b 1
)

if "%~1"=="" (
    REM No args -> interactive chat (the double-click case).
    "%PYEXE%" -m hermes_cli.main chat
) else (
    "%PYEXE%" -m hermes_cli.main %*
)

set "RC=%ERRORLEVEL%"
REM Keep the window open when double-clicked so errors are readable.
if "%~1"=="" pause
exit /b %RC%
