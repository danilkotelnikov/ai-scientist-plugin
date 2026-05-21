#!/usr/bin/env bash
# install.sh — one-time setup for ai-scientist plugin (Linux / macOS).
# Mirrors install.ps1 for Codex / non-Windows hosts.

set -euo pipefail

PLUGIN_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
AI_HOME="${AI_SCIENTIST_HOME:-$HOME/.ai-scientist}"

echo -e "\033[36mAI-Scientist plugin install starting...\033[0m"

# 1. Probe Python
if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 not in PATH. Install Python 3.11+ and re-run." >&2
    exit 1
fi
echo "  Python: $(python3 --version)"

# 2-5. Probe optional binaries
for bin in pandoc soffice pdflatex pdftoppm; do
    if command -v "$bin" >/dev/null 2>&1; then
        echo "  $bin: $(command -v "$bin")"
    else
        echo "  WARNING: $bin not found (optional — affects manuscript export / visual validation)"
    fi
done

# 6. Ensure ~/.ai-scientist/ exists
mkdir -p "$AI_HOME"
echo "  AI_SCIENTIST_HOME = $AI_HOME"

# 7. Pip-install AI-Scientist core MCP deps
echo -e "\033[36mInstalling AI-Scientist MCP requirements...\033[0m"
python3 -m pip install --user -r "$PLUGIN_ROOT/mcp/requirements.txt"

# 7-bis. MemPalace
echo -e "\033[36mInstalling MemPalace...\033[0m"
python3 -m pip install --user mempalace
mkdir -p "$AI_HOME/palace"
if command -v mempalace >/dev/null 2>&1; then
    mempalace init "$AI_HOME/palace" 2>/dev/null || true
    echo "  mempalace: $(command -v mempalace)"
    echo "  Per-project palace root: $AI_HOME/palace"
else
    echo "  WARNING: mempalace command not on PATH after install. Add ~/.local/bin to PATH or restart shell."
fi

# 7c. Probe uvx (for OpenAlex MCP)
if ! command -v uvx >/dev/null 2>&1; then
    echo "  WARNING: uvx not found. OpenAlex MCP requires uvx. Install: pip install --user uv"
else
    echo "  uvx: $(command -v uvx)"
fi

# 7d. Clone the cloned-MCPs (Semantic Scholar, bioRxiv)
mkdir -p "$AI_HOME/external"

install_git_mcp() {
    local url="$1"
    local dirname="$2"
    local entry="$3"
    local target="$AI_HOME/external/$dirname"
    if [ ! -d "$target" ]; then
        echo "  Cloning $url..."
        git clone --depth=1 "$url" "$target" 2>&1 | tail -2
    else
        echo "  $dirname already cloned at $target"
    fi
    if [ ! -f "$target/$entry" ]; then
        echo "  WARNING: $dirname clone failed (missing $entry)"
        return
    fi
    if [ -f "$target/requirements.txt" ]; then
        python3 -m pip install --user -q -r "$target/requirements.txt"
        echo "  $dirname deps installed"
    fi
}

install_git_mcp "https://github.com/JackKuo666/semanticscholar-MCP-Server.git" \
    "semanticscholar-MCP-Server" "semantic_scholar_server.py"
install_git_mcp "https://github.com/JackKuo666/bioRxiv-MCP-Server.git" \
    "bioRxiv-MCP-Server" "biorxiv_server.py"

# 7e. Env-var reminders
[ -z "${OPENALEX_EMAIL:-}" ] && echo "  WARNING: OPENALEX_EMAIL unset. Polite-pool throttle (1 req/s) will apply."
[ -z "${SEMANTIC_SCHOLAR_KEY:-}" ] && echo "  WARNING: SEMANTIC_SCHOLAR_KEY unset. Semantic Scholar /search will be skipped."

# 8. MCP self-test
echo -e "\033[36mRunning MCP self-test...\033[0m"
python3 "$PLUGIN_ROOT/mcp/server.py" --selftest

# 9. Knowledge DB stats
DB_PATH="$AI_HOME/knowledge.db"
[ -f "$DB_PATH" ] && echo "  knowledge.db: $(stat -c%s "$DB_PATH" 2>/dev/null || stat -f%z "$DB_PATH") bytes"

echo ""
echo -e "\033[32mInstall complete.\033[0m"
echo ""
echo "Codex next steps:"
echo "  1. ln -s $PLUGIN_ROOT/skills/ai-scientist ~/.agents/skills/ai-scientist"
echo "  2. ln -s $PLUGIN_ROOT/agents              ~/.agents/agents/ai-scientist"
echo "  3. Append plugins/ai-scientist/codex-config.toml.example to ~/.codex/config.toml"
echo "  4. codex restart"
