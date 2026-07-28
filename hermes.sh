#!/bin/bash
# ============================================================================
#  Hermes Agent - MTK one-click launcher (Git Bash, no WSL)
#  Usage:  ./hermes.sh            -> interactive chat
#          ./hermes.sh model      -> pick model/provider
#          ./hermes.sh doctor     -> diagnostics
#          ./hermes.sh -z "hi"    -> one-shot prompt
# ============================================================================
set -e
SCRIPT_DIR="${BASH_SOURCE[0]%/*}"
if [ "$SCRIPT_DIR" = "${BASH_SOURCE[0]}" ]; then
    SCRIPT_DIR="."
fi
cd "$SCRIPT_DIR"

# MTK environment. AIDE TLS needs the MTK CA on SSL_CERT_FILE / REQUESTS_CA_BUNDLE.
export HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
export PYTHONIOENCODING=utf-8
MTK_CA="${USERPROFILE:-$HOME}\\.claude\\skills\\references\\mtk-ca.crt"
export SSL_CERT_FILE="$MTK_CA"
export REQUESTS_CA_BUNDLE="$MTK_CA"
export NODE_EXTRA_CA_CERTS="$MTK_CA"
export HERMES_GIT_BASH_PATH="${PROGRAMFILES:-C:\Program Files}\Git\usr\bin\bash.exe"

PYEXE="./.venv/Scripts/python.exe"
if [ ! -x "$PYEXE" ]; then
    PYEXE="./venv/Scripts/python.exe"
fi
if [ ! -x "$PYEXE" ]; then
    echo "[!] venv not found at $PYEXE — rebuild it (see setup-hermes-mtk.sh)."
    exit 1
fi

prepare_base_python() {
    VENV_DIR="${PYEXE%/Scripts/python.exe}"
    BASE_HOME=""
    while IFS='=' read -r key value; do
        if [ "${key//[[:space:]]/}" = "home" ]; then
            BASE_HOME="${value#"${value%%[![:space:]]*}"}"
            break
        fi
    done < "$VENV_DIR/pyvenv.cfg"
    ROOT_WIN="$(pwd -W)"
    VENV_WIN="$ROOT_WIN/${VENV_DIR#./}"
    export HERMES_VENV_PYTHON="$ROOT_WIN/${PYEXE#./}"
    export HERMES_VENV_PREFIX="$VENV_WIN"
    export VIRTUAL_ENV="$VENV_WIN"
    export PYTHONPATH="$ROOT_WIN;$VENV_WIN/Lib/site-packages${PYTHONPATH:+;$PYTHONPATH}"
}

if [ "${1:-}" = "gateway" ]; then
    case "${2:-}" in
        start|stop|restart|status)
            prepare_base_python
            if [ -n "$BASE_HOME" ]; then
                exec "$BASE_HOME/python.exe" -m hermes_cli.gateway_control_entry "$@"
            fi
            exec "$PYEXE" -m hermes_cli.gateway_control_entry "$@"
            ;;
    esac
fi

if [ "$#" -eq 1 ] && [ "$1" = "--tui" ]; then
    TUI_ENTRY="./ui-tui/dist/entry.js"
    NODE_BIN="${USERPROFILE:-$HOME}/.cchelper/nodejs/node.exe"
    if [ ! -x "$NODE_BIN" ]; then
        if command -v node >/dev/null 2>&1; then
            NODE_BIN=node
        else
            NODE_BIN=""
        fi
    fi
    if [ -n "$NODE_BIN" ] && [ -f "$TUI_ENTRY" ]; then
        export HERMES_PYTHON="$PYEXE"
        export HERMES_TUI_GATEWAY_PYTHON="$PYEXE"
        export VIRTUAL_ENV="${PYEXE%/Scripts/python.exe}"
        export NODE_ENV=production
        case " ${NODE_OPTIONS:-} " in
            *" --max-old-space-size="*) ;;
            *) export NODE_OPTIONS="${NODE_OPTIONS:+$NODE_OPTIONS }--max-old-space-size=8192" ;;
        esac
        exec "$NODE_BIN" --expose-gc "$TUI_ENTRY"
    fi
fi

if [ "$#" -eq 0 ]; then
    exec "$PYEXE" -m hermes_cli.main chat
else
    exec "$PYEXE" -m hermes_cli.main "$@"
fi
