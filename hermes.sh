#!/bin/bash
# ============================================================================
#  Hermes Agent - MTK one-click launcher (Git Bash, no WSL)
#  Usage:  ./hermes.sh            -> interactive chat
#          ./hermes.sh model      -> pick model/provider
#          ./hermes.sh doctor     -> diagnostics
#          ./hermes.sh -z "hi"    -> one-shot prompt
# ============================================================================
set -e
cd "$(dirname "${BASH_SOURCE[0]}")"

# MTK environment. AIDE TLS needs the MTK CA on SSL_CERT_FILE / REQUESTS_CA_BUNDLE.
export HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
export PYTHONIOENCODING=utf-8
MTK_CA="$(cygpath -m "$HOME/.claude/skills/references/mtk-ca.crt" 2>/dev/null || echo "$HOME/.claude/skills/references/mtk-ca.crt")"
export SSL_CERT_FILE="$MTK_CA"
export REQUESTS_CA_BUNDLE="$MTK_CA"
export NODE_EXTRA_CA_CERTS="$MTK_CA"

PYEXE="./venv/Scripts/python.exe"
if [ ! -x "$PYEXE" ]; then
    echo "[!] venv not found at $PYEXE — rebuild it (see setup-hermes-mtk.sh)."
    exit 1
fi

if [ "$#" -eq 0 ]; then
    exec "$PYEXE" -m hermes_cli.main chat
else
    exec "$PYEXE" -m hermes_cli.main "$@"
fi
