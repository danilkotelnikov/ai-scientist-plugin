#!/usr/bin/env bash
# scripts/bootstrap.sh -- one-command installer for vedix plugin (v3.0+).
#
# Usage (interactive):
#   curl -fsSL https://raw.githubusercontent.com/danilkotelnikov/vedix/master/scripts/bootstrap.sh | bash
#
# Usage (non-interactive, scripted -- pick exact hosts):
#   AISP_HOSTS=claude,codex bash bootstrap.sh
#   AISP_HOSTS=all          bash bootstrap.sh
#   AISP_HOSTS=none         bash bootstrap.sh
#
# Detects Claude Code / Codex CLI / Gemini CLI in ~/.{claude,codex,gemini}/.
# By default prompts for which detected hosts to register. Idempotent.

set -e
set -o pipefail

REPO_URL="https://github.com/danilkotelnikov/vedix.git"
BRANCH="master"
AI_HOME="$HOME/.vedix"
REPO_DIR="$AI_HOME/repo"
PALACE_DIR="$AI_HOME/palace"

# Per-host install timeout (seconds). Gemini's extension install in particular
# is known to hang; keep this generous but bounded.
PER_HOST_TIMEOUT="${AISP_PER_HOST_TIMEOUT:-90}"

step() { printf "  \033[36m%s\033[0m\n" "$1"; }
ok()   { printf "  \033[32m[OK]\033[0m   %s\n" "$1"; }
note() { printf "  \033[33m[NOTE]\033[0m %s\n" "$1"; }
fail() { printf "  \033[31m[FAIL]\033[0m %s\n" "$1"; }

# Detect installed CLI hosts. Sets globals: detected_claude / codex / gemini.
detect_hosts() {
    detected_claude=0; detected_codex=0; detected_gemini=0
    [ -d "$HOME/.claude" ] && detected_claude=1
    [ -d "$HOME/.codex" ]  && detected_codex=1
    [ -d "$HOME/.gemini" ] && detected_gemini=1
}

# Parse a comma/space-separated host spec ("all", "none", "claude codex", etc.)
# against the detected hosts. Sets globals: selected_claude / codex / gemini.
parse_selection() {
    local spec="${1:-}"
    selected_claude=0; selected_codex=0; selected_gemini=0
    spec="$(printf "%s" "$spec" | tr '[:upper:]' '[:lower:]' | tr ',' ' ')"
    if [ -z "${spec// /}" ]; then return; fi
    if [ "$spec" = "none" ]; then return; fi
    if [ "$spec" = "all" ] || [ "$spec" = "*" ]; then
        [ "$detected_claude" = "1" ] && selected_claude=1
        [ "$detected_codex"  = "1" ] && selected_codex=1
        [ "$detected_gemini" = "1" ] && selected_gemini=1
        return
    fi
    for tok in $spec; do
        case "$tok" in
            1|c|cl|claude|claude.code|claude_code) [ "$detected_claude" = "1" ] && selected_claude=1 ;;
            2|x|cx|codex|codex.cli)                [ "$detected_codex"  = "1" ] && selected_codex=1  ;;
            3|g|ge|gem|gemini|gemini.cli)          [ "$detected_gemini" = "1" ] && selected_gemini=1 ;;
            *) note "Unknown host token: '$tok' (ignored)" ;;
        esac
    done
}

# Interactive picker (only when stdin is a tty AND AISP_HOSTS is unset).
prompt_selection() {
    if [ "$detected_claude" = "0" ] && [ "$detected_codex" = "0" ] && [ "$detected_gemini" = "0" ]; then
        note "No CLI hosts detected (~/.claude, ~/.codex, ~/.gemini all absent)."
        note "The bootstrap will install Python deps + run --selftest only."
        return
    fi
    echo
    printf "\033[35mDetected agent CLI hosts on this machine:\033[0m\n"
    [ "$detected_claude" = "1" ] && echo "  [1] Claude Code (~/.claude/)"
    [ "$detected_codex"  = "1" ] && echo "  [2] Codex CLI    (~/.codex/)"
    [ "$detected_gemini" = "1" ] && echo "  [3] Gemini CLI   (~/.gemini/)"
    echo
    echo "Which hosts should I install vedix into?"
    echo "  - Enter numbers separated by spaces or commas (e.g. '1 2', '1,3')"
    echo "  - 'all' or empty (Enter): every detected host"
    echo "  - 'none': skip all host registration"
    echo
    if [ -t 0 ]; then
        # stdin is a tty -- read interactively from the user.
        printf "  Your choice: "
        read -r answer
    else
        # piped (curl | bash) -- try /dev/tty for the prompt; fall back to "all".
        if [ -r /dev/tty ]; then
            printf "  Your choice: " >/dev/tty
            read -r answer </dev/tty
        else
            note "stdin is piped and /dev/tty unavailable -- defaulting to 'all'"
            answer="all"
        fi
    fi
    if [ -z "${answer// /}" ]; then answer="all"; fi
    parse_selection "$answer"
}

# Run a command with a wall-clock timeout (uses GNU coreutils 'timeout' if
# available; falls back to perl alarm or background-kill otherwise).
run_with_timeout() {
    local secs="$1"; shift
    if command -v timeout >/dev/null 2>&1; then
        timeout --kill-after=10 "$secs" "$@"
        return $?
    fi
    if command -v gtimeout >/dev/null 2>&1; then
        gtimeout --kill-after=10 "$secs" "$@"
        return $?
    fi
    # Fallback: background + kill
    "$@" &
    local pid=$!
    ( sleep "$secs"; kill -TERM "$pid" 2>/dev/null; sleep 5; kill -KILL "$pid" 2>/dev/null ) &
    local watcher=$!
    wait "$pid" 2>/dev/null
    local rc=$?
    kill "$watcher" 2>/dev/null
    return $rc
}

# ============================================================================

echo
printf "\033[35mVedix -- one-command bootstrap\033[0m\n"
echo

# 1. Probe prerequisites
step "Probing prerequisites"
if command -v python3 >/dev/null 2>&1; then PYTHON=python3
elif command -v python >/dev/null 2>&1; then PYTHON=python
else fail "Python 3.11+ not found. Install via your package manager."; exit 1; fi
command -v git >/dev/null 2>&1 || { fail "git not found"; exit 1; }
ok "python: $($PYTHON --version 2>&1)"
ok "git:    $(git --version 2>&1)"

# 2. Detect hosts and decide selection (env override > interactive prompt)
detect_hosts
if [ -n "${AISP_HOSTS:-}" ]; then
    parse_selection "$AISP_HOSTS"
    step "Host selection from \$AISP_HOSTS = '$AISP_HOSTS'"
    [ "$selected_claude" = "1" ] && ok "claude -- selected" || { [ "$detected_claude" = "1" ] && note "claude -- detected but not selected"; }
    [ "$selected_codex"  = "1" ] && ok "codex  -- selected" || { [ "$detected_codex"  = "1" ] && note "codex  -- detected but not selected"; }
    [ "$selected_gemini" = "1" ] && ok "gemini -- selected" || { [ "$detected_gemini" = "1" ] && note "gemini -- detected but not selected"; }
else
    prompt_selection
fi

# 3. Clone or update the canonical repo
step "Syncing canonical repo at $REPO_DIR"
mkdir -p "$AI_HOME"
if [ -d "$REPO_DIR/.git" ]; then
    pushd "$REPO_DIR" >/dev/null
    git stash push --include-untracked -m "auto-stash by bootstrap.sh $(date -Iseconds)" >/dev/null 2>&1 || true
    git fetch --quiet origin "$BRANCH" >/dev/null 2>&1 || true
    git reset --hard "origin/$BRANCH" --quiet >/dev/null 2>&1 || true
    popd >/dev/null
    ok "Updated existing clone (any local changes saved as a stash)"
else
    git clone --quiet --branch "$BRANCH" "$REPO_URL" "$REPO_DIR"
    ok "Cloned fresh"
fi

PLUG="$REPO_DIR/plugins/vedix"

# 4. Install Python dependencies (idempotent, --user)
step "Installing Python dependencies (user-site)"
$PYTHON -m pip install --user --quiet -r "$PLUG/mcp/requirements.txt" >/dev/null 2>&1 || \
    note "pip install requirements may have failed; check $PYTHON -m pip output"
ok "MCP requirements present"

$PYTHON -m pip install --user --quiet mempalace >/dev/null 2>&1 || \
    note "pip install mempalace may have failed"
ok "mempalace package present"

mkdir -p "$PALACE_DIR"
if command -v mempalace >/dev/null 2>&1; then
    mempalace init "$PALACE_DIR" >/dev/null 2>&1 || true
    ok "MemPalace initialized at $PALACE_DIR"
else
    note "mempalace CLI not on PATH yet; reopen the shell or update PATH"
fi

# 4d. Run the plugin's own install.sh so the two cloned MCPs
# (semanticscholar-MCP-Server + bioRxiv-MCP-Server) get cloned into
# ~/.vedix/external/. The bootstrap previously skipped this,
# leaving those two MCPs broken on first use.
step "Running plugin install.sh (provisions semanticscholar + biorxiv git clones)"
if bash "$PLUG/scripts/install.sh" 2>&1; then
    ok "Plugin install.sh completed"
else
    note "Plugin install.sh reported errors -- check output above"
fi

# 5. Codex CLI -- auto-merge config + symlinks (only if selected)
if [ "$selected_codex" = "1" ]; then
    echo
    step "Registering plugin into Codex CLI"

    CODEX_CLONE="$HOME/.codex/vedix"
    if [ ! -e "$CODEX_CLONE" ]; then
        ln -s "$REPO_DIR" "$CODEX_CLONE"
        ok "Symlinked ~/.codex/vedix -> $REPO_DIR"
    else
        ok "~/.codex/vedix already present"
    fi

    mkdir -p "$HOME/.agents/skills" "$HOME/.agents/agents"
    rm -rf "$HOME/.agents/skills/vedix" "$HOME/.agents/agents/vedix" 2>/dev/null || true
    ln -sf "$PLUG/skills/ai-scientist" "$HOME/.agents/skills/vedix"
    ln -sf "$PLUG/agents"              "$HOME/.agents/agents/vedix"
    ok "Symlinked skill + agents into ~/.agents/"

    CONFIG_TOML="$HOME/.codex/config.toml"
    $PYTHON "$REPO_DIR/scripts/_merge_codex_config.py" \
        --user "$CONFIG_TOML" \
        --example "$PLUG/codex-config.toml.example" \
        --quiet
    ok "config.toml merged (sentinel-bracketed; idempotent)"
elif [ "$detected_codex" = "1" ]; then
    note "Codex CLI present but not selected -- skipping"
fi

# 6. Gemini CLI (only if selected) -- with timeout
if [ "$selected_gemini" = "1" ]; then
    echo
    step "Registering plugin into Gemini CLI (timeout: ${PER_HOST_TIMEOUT}s)"
    if command -v gemini >/dev/null 2>&1; then
        if run_with_timeout "$PER_HOST_TIMEOUT" gemini extensions install "$REPO_URL" >/dev/null 2>&1; then
            ok "Gemini extension installed"
        else
            note "Gemini install timed out or failed -- skipping. Re-run later: gemini extensions install $REPO_URL"
        fi
    else
        note "gemini CLI not on PATH; install Gemini CLI then re-run this bootstrap"
    fi
elif [ "$detected_gemini" = "1" ]; then
    note "Gemini CLI present but not selected -- skipping"
fi

# 7. Claude Code (only if selected) -- print the slash commands
if [ "$selected_claude" = "1" ]; then
    echo
    step "Claude Code selected"
    note "Open a Claude Code session and paste these two slash commands:"
    printf "      /plugin marketplace add danilkotelnikov/vedix\n"
    printf "      /plugin install vedix@vedix\n"
    note "Slash commands cannot be issued from outside the agent session."
elif [ "$detected_claude" = "1" ]; then
    note "Claude Code present but not selected -- skipping"
fi

# 8. MCP self-test
echo
step "Running MCP self-test"
SELFTEST_OUT=$($PYTHON "$PLUG/mcp/server.py" --selftest 2>&1 || true)
if printf "%s" "$SELFTEST_OUT" | grep -q "selftest: OK"; then
    ok "$(printf "%s" "$SELFTEST_OUT" | tr '\n' ';')"
else
    note "self-test output: $SELFTEST_OUT"
fi

# 9. Probe required env var
echo
step "Environment variables"
if [ -z "${OPENALEX_EMAIL:-}" ]; then
    note "OPENALEX_EMAIL is not set. Add to your shell rc:"
    printf "      echo 'export OPENALEX_EMAIL=\"you@example.com\"' >> ~/.bashrc\n"
    note "(required since 2026-02-13 for OpenAlex API; restart shell after setting)"
else
    ok "OPENALEX_EMAIL = $OPENALEX_EMAIL"
fi
for v in SEMANTIC_SCHOLAR_KEY ANNAS_BASE_URL ANNAS_DOWNLOAD_PATH ANNAS_SECRET_KEY; do
    val=$(printenv "$v" || true)
    if [ -n "$val" ]; then ok "$v = (set)"; else note "$v not set (optional)"; fi
done

# B1: v2 -> v3 migration (Vedix rename)
if [ -d "$HOME/.ai-scientist" ] && [ ! -d "$HOME/.vedix" ]; then
    echo
    step "Detected v2.x install at ~/.ai-scientist -- running migration helper"
    $PYTHON "$REPO_DIR/scripts/migrate_v2_to_v3.py" || \
        note "migration helper exited non-zero -- inspect output above"
fi

echo
printf "\033[32mBootstrap complete.\033[0m\n"
echo "  - canonical repo: $REPO_DIR"
echo "  - re-run anytime: same one-liner (idempotent)"
echo "  - skip the prompt next time: AISP_HOSTS=claude,codex bash bootstrap.sh   (or all/none)"
echo
