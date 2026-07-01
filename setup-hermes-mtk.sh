#!/bin/bash
# ============================================================================
# Hermes Agent - MTK Environment Setup Script
# ============================================================================
# Adapts the original setup-hermes.sh for MediaTek internal environment:
#
#   - Windows 11 + Git Bash (no WSL required)
#   - MTK PyPI mirror (oa-mirror.mediatek.inc) — no direct pypi.org access
#   - MTK CA certificate injection into certifi bundle
#   - MTK AIDE Gateway as LLM provider (OpenAI-compatible)
#   - cp950 encoding fix for Windows terminals
#   - NODE_EXTRA_CA_CERTS for Node.js HTTPS
#   - Skips: Docker, Modal, Daytona, Singularity, external messaging platforms
#   - Teams integration via existing ~/.teams-tokens/ skill auth
#
# Usage:
#   cd "E:/01_Job/Tool/Hermes Agent"
#   ./setup-hermes-mtk.sh
# ============================================================================

set -e

GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

MTK_CA="C:/Users/${USERNAME}/.claude/skills/references/mtk-ca.crt"
MTK_PIP_CERT="E:/06_Tool/PIP certificate/cacertmtk.pem"
MTK_PIP_INDEX="http://oa-mirror.mediatek.inc/repository/pypi/simple"
MTK_PIP_HOST="oa-mirror.mediatek.inc"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"

echo ""
echo -e "${CYAN}Hermes Agent - MTK Setup${NC}"
echo ""

# ============================================================================
# 1. Check Python
# ============================================================================
echo -e "${CYAN}->  Checking Python...${NC}"
if ! command -v python &>/dev/null; then
    echo -e "${RED}x  Python not found. Install Python 3.11+ from python.org${NC}"
    exit 1
fi
PY_VER=$(python -c 'import sys; print(sys.version_info >= (3,11))' 2>/dev/null)
if [ "$PY_VER" != "True" ]; then
    echo -e "${RED}x  Python 3.11+ required (found: $(python --version))${NC}"
    exit 1
fi
echo -e "${GREEN}v  $(python --version)${NC}"

# ============================================================================
# 2. Check uv (install via pip if missing)
# ============================================================================
echo -e "${CYAN}->  Checking uv...${NC}"
if ! command -v uv &>/dev/null; then
    echo -e "${CYAN}->  Installing uv via pip (MTK mirror)...${NC}"
    pip install uv \
        --index-url "$MTK_PIP_INDEX" \
        --trusted-host "$MTK_PIP_HOST" \
        --cert "$MTK_PIP_CERT" \
        -q
fi
echo -e "${GREEN}v  $(uv --version)${NC}"

# ============================================================================
# 3. Virtual environment
# ============================================================================
echo -e "${CYAN}->  Setting up virtual environment...${NC}"
if [ -d "venv" ]; then
    echo -e "${CYAN}->  Removing existing venv...${NC}"
    rm -rf venv
fi
uv venv venv --python 3.12
echo -e "${GREEN}v  venv created (Python 3.12)${NC}"

# Activate and ensure pip is available inside venv
source venv/Scripts/activate
uv pip install \
    --index-url "$MTK_PIP_INDEX" \
    --native-tls \
    pip setuptools wheel -q
echo -e "${GREEN}v  pip installed in venv${NC}"

# ============================================================================
# 4. MTK CA cert injection into certifi
# ============================================================================
echo -e "${CYAN}->  Injecting MTK CA certificate into certifi...${NC}"
python -c "
import certifi, pathlib
ca_path = pathlib.Path('$MTK_CA')
if not ca_path.exists():
    print('  WARNING: MTK CA not found at $MTK_CA')
    exit(0)
bundle = pathlib.Path(certifi.where())
bundle_text = bundle.read_text()
ca_text = ca_path.read_text()
if 'MIIDjjCCAnag' not in bundle_text:
    with open(bundle, 'a') as f:
        f.write('\n' + ca_text)
    print('  MTK CA injected')
else:
    print('  MTK CA already present')
"

# ============================================================================
# 5. Install Python dependencies
# ============================================================================
echo -e "${CYAN}->  Installing Python dependencies (MTK mirror)...${NC}"
# Core + MTK-compatible extras (skip: voice, matrix, modal, daytona, rl)
python -m pip install -e ".[messaging,cron,cli,pty,mcp,web,mistral,bedrock,honcho,acp,slack]" \
    --index-url "$MTK_PIP_INDEX" \
    --trusted-host "$MTK_PIP_HOST" \
    --cert "$MTK_PIP_CERT" \
    -q
echo -e "${GREEN}v  Python dependencies installed${NC}"

# ============================================================================
# 6. Node.js dependencies (agent-browser + TUI)
# ============================================================================
echo -e "${CYAN}->  Installing Node.js dependencies...${NC}"
if command -v npm &>/dev/null; then
    npm install --silent 2>/dev/null && echo -e "${GREEN}v  agent-browser installed${NC}" || \
        echo -e "${YELLOW}!  npm install failed (browser tools may not work)${NC}"

    if [ -f "ui-tui/package.json" ]; then
        cd ui-tui && npm install --silent 2>/dev/null && \
            echo -e "${GREEN}v  TUI dependencies installed${NC}" || \
            echo -e "${YELLOW}!  TUI npm install failed (--tui mode may not work)${NC}"
        cd "$SCRIPT_DIR"
    fi
else
    echo -e "${YELLOW}!  npm not found (browser tools will not work)${NC}"
fi

# ============================================================================
# 7. Sync bundled skills
# ============================================================================
echo -e "${CYAN}->  Syncing bundled skills...${NC}"
PYTHONIOENCODING=utf-8 python tools/skills_sync.py 2>/dev/null && \
    echo -e "${GREEN}v  Skills synced to ~/.hermes/skills/${NC}" || \
    ([ -d skills ] && cp -rn skills/* "$HERMES_HOME/skills/" 2>/dev/null; \
     echo -e "${GREEN}v  Skills copied to ~/.hermes/skills/${NC}")

# ============================================================================
# 8. Create ~/.hermes directory structure
# ============================================================================
echo -e "${CYAN}->  Creating ~/.hermes directories...${NC}"
mkdir -p "$HERMES_HOME"/{cron,sessions,logs,pairing,hooks,image_cache,audio_cache,memories,skills,whatsapp/session}
echo -e "${GREEN}v  ~/.hermes/ structure ready${NC}"

# ============================================================================
# 9. Config files from templates
# ============================================================================
echo -e "${CYAN}->  Setting up config files...${NC}"

if [ ! -f "$HERMES_HOME/.env" ]; then
    cat > "$HERMES_HOME/.env" << 'ENVEOF'
# =============================================================================
# MTK AIDE Gateway
# =============================================================================
# TODO: Fill in your AIDE JWT token (from config.ini [primary] section)
#       Token expires in ~7 days
AIDE_API_KEY=FILL_YOUR_AIDE_JWT_TOKEN_HERE

# Terminal
TERMINAL_TIMEOUT=180
TERMINAL_LIFETIME_SECONDS=300

# Encoding fix for Windows (cp950 cannot handle emoji)
PYTHONIOENCODING=utf-8

# Debug (all off)
WEB_TOOLS_DEBUG=false
VISION_TOOLS_DEBUG=false
MOA_TOOLS_DEBUG=false
IMAGE_TOOLS_DEBUG=false
ENVEOF
    echo -e "${GREEN}v  Created ~/.hermes/.env${NC}"
else
    echo -e "${GREEN}v  ~/.hermes/.env already exists${NC}"
fi

if [ ! -f "$HERMES_HOME/config.yaml" ]; then
    cat > "$HERMES_HOME/config.yaml" << 'YAMLEOF'
# Hermes Agent - MTK Environment Configuration
_config_version: 19

model:
  default: "gpt-4o"
  provider: "custom:aide"

providers:
  aide:
    name: "MTK AIDE Gateway"
    base_url: "https://mlop-azure-gateway.mediatek.inc/llm/v3"
    key_env: "AIDE_API_KEY"
    model: "gpt-4o"
    default_headers:
      api-key: "${AIDE_API_KEY}"
  aide-v1:
    name: "MTK AIDE Gateway (multi-vendor)"
    base_url: "https://mlop-azure-gateway.mediatek.inc/v1"
    key_env: "AIDE_API_KEY"
    default_headers:
      api-key: "${AIDE_API_KEY}"

terminal:
  backend: "local"
  cwd: "."
  timeout: 180
  lifetime_seconds: 300
  persistent_shell: true
  container_cpu: 1
  container_memory: 5120
  container_disk: 51200
  container_persistent: true

compression:
  enabled: true
  threshold: 0.50
  target_ratio: 0.20
  protect_last_n: 20

auxiliary:
  vision:
    provider: "main"
    timeout: 120
  web_extract:
    provider: "main"
    timeout: 360
  compression:
    provider: "main"
    timeout: 120
  session_search:
    provider: "main"
    timeout: 30
  approval:
    provider: "main"
    timeout: 30
  flush_memories:
    provider: "main"
    timeout: 30
  title_generation:
    provider: "main"
    timeout: 30

memory:
  memory_enabled: true
  user_profile_enabled: true
  memory_char_limit: 2200
  user_char_limit: 1375
  nudge_interval: 10
  flush_min_turns: 6

agent:
  max_turns: 60
  verbose: false
  reasoning_effort: "medium"

platform_toolsets:
  cli: [terminal, file, skills, todo, tts, cronjob, memory, session_search]

skills:
  creation_nudge_interval: 15

session_reset:
  mode: both
  idle_minutes: 1440
  at_hour: 4

code_execution:
  timeout: 300
  max_tool_calls: 50

delegation:
  max_iterations: 50
  default_toolsets: ["terminal", "file"]

timezone: "Asia/Taipei"

display:
  compact: false
  streaming: true
  skin: default
YAMLEOF
    echo -e "${GREEN}v  Created ~/.hermes/config.yaml${NC}"
else
    echo -e "${GREEN}v  ~/.hermes/config.yaml already exists${NC}"
fi

# ============================================================================
# 10. Shell environment (.bashrc)
# ============================================================================
echo -e "${CYAN}->  Updating ~/.bashrc...${NC}"
BASHRC="$HOME/.bashrc"

add_if_missing() {
    local marker="$1"
    local content="$2"
    if ! grep -q "$marker" "$BASHRC" 2>/dev/null; then
        echo "$content" >> "$BASHRC"
        echo -e "${GREEN}v  Added: $marker${NC}"
    else
        echo -e "${GREEN}v  Already present: $marker${NC}"
    fi
}

add_if_missing "PYTHONIOENCODING" 'export PYTHONIOENCODING=utf-8'
add_if_missing "SSL_CERT_FILE" "export SSL_CERT_FILE=\"$MTK_CA\""
add_if_missing "REQUESTS_CA_BUNDLE" "export REQUESTS_CA_BUNDLE=\"$MTK_CA\""
add_if_missing "NODE_EXTRA_CA_CERTS" "export NODE_EXTRA_CA_CERTS=\"$MTK_CA\""
add_if_missing "alias hermes=" "alias hermes='source \"$SCRIPT_DIR/venv/Scripts/activate\" && PYTHONIOENCODING=utf-8 hermes'"

# ============================================================================
# 11. PATH setup — symlink hermes into ~/.local/bin
# ============================================================================
echo -e "${CYAN}->  Setting up hermes command in PATH...${NC}"
HERMES_BIN="$SCRIPT_DIR/venv/Scripts/hermes.exe"
LOCAL_BIN="$HOME/.local/bin"
mkdir -p "$LOCAL_BIN"

# On Windows/Git Bash, create a wrapper script instead of a symlink
cat > "$LOCAL_BIN/hermes" << WRAPEOF
#!/bin/bash
source "$SCRIPT_DIR/venv/Scripts/activate"
PYTHONIOENCODING=utf-8 hermes "\$@"
WRAPEOF
chmod +x "$LOCAL_BIN/hermes"

# Ensure ~/.local/bin is on PATH
add_if_missing '\.local/bin' 'export PATH="$HOME/.local/bin:$PATH"'
echo -e "${GREEN}v  hermes wrapper created at ~/.local/bin/hermes${NC}"

# ============================================================================
# Done
# ============================================================================
echo ""
echo -e "${GREEN}Setup complete!${NC}"
echo ""
echo "Next steps:"
echo ""
echo "  1. Fill in your AIDE JWT token:"
echo "     Edit ~/.hermes/.env  (AIDE_API_KEY=your-token-here)"
echo "     Token is in your config.ini [primary] section"
echo ""
echo "  2. Reload your shell:"
echo "     source ~/.bashrc"
echo ""
echo "  3. Run diagnostics:"
echo "     hermes doctor"
echo ""
echo "  4. Start chatting:"
echo "     hermes"
echo ""
echo "Notes:"
echo "  - Model:    MTK AIDE Gateway /llm/v3/ (gpt-4o default)"
echo "  - Terminal: local (Windows Git Bash)"
echo "  - Skills:   77 bundled skills synced"
echo "  - Encoding: PYTHONIOENCODING=utf-8 (emoji support)"
echo "  - Teams:    use 'hermes skills' to load teams skill"
echo ""
