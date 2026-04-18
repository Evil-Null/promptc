#!/usr/bin/env bash
# promptc — one-command install & setup
# Usage: curl -sSL https://raw.githubusercontent.com/Evil-Null/promptc/main/install.sh | bash
#   or:  ./install.sh          (from cloned repo)
#   or:  ./install.sh --local  (install from local source instead of PyPI)
set -euo pipefail

BLUE='\033[0;34m'
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${BLUE}ℹ${NC}  $*"; }
ok()    { echo -e "${GREEN}✅${NC} $*"; }
warn()  { echo -e "${YELLOW}⚠️${NC}  $*"; }
fail()  { echo -e "${RED}❌${NC} $*"; exit 1; }

echo ""
echo -e "${BLUE}╔══════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     promptc — install & setup        ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════╝${NC}"
echo ""

# --- Prerequisites ---
command -v python3 >/dev/null 2>&1 || fail "Python 3 is required. Install: sudo apt install python3"

PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)

if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 11 ]; }; then
    fail "Python 3.11+ required (found $PY_VERSION)"
fi
ok "Python $PY_VERSION"

# --- Install pipx if missing ---
if ! command -v pipx >/dev/null 2>&1; then
    info "Installing pipx..."
    python3 -m pip install --user pipx >/dev/null 2>&1
    python3 -m pipx ensurepath >/dev/null 2>&1
    export PATH="$HOME/.local/bin:$PATH"
    ok "pipx installed"
else
    ok "pipx available"
fi

# --- Install prompt-compiler ---
if [ "${1:-}" = "--local" ]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    info "Installing from local source: $SCRIPT_DIR"
    pipx install --force "${SCRIPT_DIR}[mcp]" 2>/dev/null || pipx install --force "$SCRIPT_DIR" 2>/dev/null
else
    info "Installing from PyPI..."
    pipx install --force "prompt-compiler[mcp]" 2>/dev/null || pipx install --force prompt-compiler 2>/dev/null
fi

# Ensure PATH includes pipx bin
export PATH="$HOME/.local/bin:$PATH"

if command -v promptc-mcp >/dev/null 2>&1; then
    INSTALLED_VERSION=$(promptc-mcp --version 2>/dev/null || echo "unknown")
    ok "promptc-mcp installed ($INSTALLED_VERSION)"
else
    fail "promptc-mcp not found after install. Check: export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

# --- Register in Copilot CLI ---
COPILOT_CONFIG="$HOME/.copilot/mcp-config.json"
BINARY_PATH=$(command -v promptc-mcp)

if [ -f "$COPILOT_CONFIG" ]; then
    if python3 -c "
import json, sys
with open('$COPILOT_CONFIG') as f:
    d = json.load(f)
if 'promptc' in d.get('mcpServers', {}):
    sys.exit(0)
sys.exit(1)
" 2>/dev/null; then
        ok "Already registered in Copilot CLI config"
    else
        info "Registering in Copilot CLI..."
        python3 -c "
import json
path = '$COPILOT_CONFIG'
with open(path) as f:
    d = json.load(f)
d.setdefault('mcpServers', {})
d['mcpServers']['promptc'] = {'command': '$BINARY_PATH', 'args': []}
with open(path, 'w') as f:
    json.dump(d, f, indent=2)
    f.write('\n')
"
        ok "Registered in $COPILOT_CONFIG"
    fi
else
    info "Creating Copilot CLI config..."
    mkdir -p "$(dirname "$COPILOT_CONFIG")"
    python3 -c "
import json
d = {'mcpServers': {'promptc': {'command': '$BINARY_PATH', 'args': []}}}
with open('$COPILOT_CONFIG', 'w') as f:
    json.dump(d, f, indent=2)
    f.write('\n')
"
    ok "Created $COPILOT_CONFIG with promptc MCP"
fi

# --- Verify ---
echo ""
info "Running verification..."
promptc-mcp --verify 2>&1 || true

echo ""
echo -e "${GREEN}╔══════════════════════════════════════╗${NC}"
echo -e "${GREEN}║     ✅ Installation complete!        ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════╝${NC}"
echo ""
echo "  Next steps:"
echo "    1. Restart Copilot CLI (exit + reopen)"
echo "    2. Try: \"use promptc_templates to list templates\""
echo ""
