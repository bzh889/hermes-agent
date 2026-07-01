@echo off
REM ============================================================================
REM  Hermes Agent - MTK one-click launcher (Windows, no WSL)
REM  Double-click  -> opens interactive chat in Windows Terminal (proper VT
REM                   console; the plain double-click conhost can't drive the
REM                   prompt_toolkit TUI, so we relaunch in wt.exe).
REM  From a shell  -> hermes.bat model | doctor | -z "hi"  (runs in place)
REM ============================================================================
cd /d "%~dp0"

REM --- MTK environment (a double-click does NOT inherit ~/.bashrc) ---
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

REM Explicit args (invoked from a terminal): run in place.
if not "%~1"=="" (
    "%PYEXE%" -m hermes_cli.main %*
    exit /b
)

REM Already relaunched inside Windows Terminal: go straight to chat.
if "%HERMES_WT%"=="1" goto :chat

REM Bare double-click: relaunch inside Windows Terminal for a real VT console.
where wt.exe >nul 2>&1
if %errorlevel%==0 (
    wt.exe -d "%~dp0." cmd /k "set HERMES_WT=1 & hermes.bat"
    exit /b
)

:chat
"%PYEXE%" -m hermes_cli.main chat
pause
exit /b
