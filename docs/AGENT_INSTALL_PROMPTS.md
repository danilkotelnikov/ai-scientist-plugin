# LLM-Driven Install Prompts

Copy-paste these prompts to any agent (Codex, Gemini, Claude Code) and it will install the ai-scientist plugin end-to-end. Each prompt is **self-contained** — the agent doesn't need prior context. Each prompt sources the host-specific install guide and references the per-MCP configuration checklist below.

---

## Per-MCP configuration checklist (referenced by every install prompt)

The plugin ships **9 MCP servers**. Each has a different install path, env-var requirement, and verification probe. Any install prompt MUST run through this checklist before declaring success.

| # | MCP server | Install method | Required env vars | Optional env vars | Verification |
|---|---|---|---|---|---|
| 1 | `ai-scientist` | bundled in plugin (Python module under `mcp/server.py`) | none | `AI_SCIENTIST_HOME` (default `~/.ai-scientist`) | `python <plugin>/mcp/server.py --selftest` returns exit 0 |
| 2 | `mempalace` | `pip install mempalace` | none | `MEMPALACE_ROOT` (default `~/.ai-scientist/palace`) | `mempalace --version` and check `which mempalace-mcp` |
| 3 | `openalex` | `uvx --from git+https://github.com/drAbreu/alex-mcp.git@4.1.0 alex-mcp` (auto on first MCP launch) | `OPENALEX_MAILTO` (= polite-pool email) | `OPENALEX_RATE_PER_SEC` (default 10) | After registering the MCP, call `mcp__openalex__search_works(query="test", per_page=1)` — should return 1 work without error |
| 4 | `semanticscholar` | git clone `JackKuo666/semanticscholar-MCP-Server` to `~/.ai-scientist/external/`, pip install requirements | `SEMANTIC_SCHOLAR_API_KEY` (required for `/search` since late 2024; without it, `/paper/{id}` lookups still work) | none | After registering, call `mcp__semanticscholar__search_semantic_scholar(query="test", limit=1)` — returns 1 paper if key set, else error message |
| 5 | `arxiv` | `uvx arxiv-mcp-server` (auto on first launch) | none | none | Call `mcp__arxiv__search_papers(query="test", max_results=1)` — returns 1 paper |
| 6 | `biorxiv` | git clone `JackKuo666/bioRxiv-MCP-Server` to `~/.ai-scientist/external/`, pip install requirements | none | none | Call `mcp__biorxiv__search_preprints(query="test")` — returns preprints |
| 7 | `pubmed` | `npx -y pubmed-mcp` (auto on first launch) | none | none | Call `mcp__pubmed__search_articles(query="test")` |
| 8 | `annas-mcp` | `npx -y annas-mcp mcp` (auto on first launch) | none for search; full-text needs `ANNAS_BASE_URL`, `ANNAS_DOWNLOAD_PATH`, `ANNAS_SECRET_KEY` | same | Call `mcp__annas-mcp__article_search(query="test")` |
| 9 | `fetcher` | `npx -y fetcher-mcp` (auto on first launch) | none | none | Call `mcp__fetcher__fetch_url(url="https://api.openalex.org/works?per-page=1")` |

**The two cloned MCPs (`semanticscholar`, `biorxiv`)** require their repos to live at:

- `~/.ai-scientist/external/semanticscholar-MCP-Server/`
- `~/.ai-scientist/external/bioRxiv-MCP-Server/`

The install script (`scripts/install.sh` or `install.ps1`) clones both. If the clone path differs, the agent must update the corresponding `args` path in the host config (`.mcp.json` / `~/.codex/config.toml` / `gemini-extension.json`).

**Env-var verification step (any host):**

```bash
# Required
[ -z "$OPENALEX_EMAIL" ] && echo "WARN: OPENALEX_EMAIL unset → polite-pool throttle 1 req/s instead of 10"

# Optional but unblock /search endpoints
[ -z "$SEMANTIC_SCHOLAR_KEY" ] && echo "INFO: SEMANTIC_SCHOLAR_KEY unset → Semantic Scholar /search will be skipped"

# Optional: only needed for full-text article downloads via Anna's Archive
[ -z "$ANNAS_SECRET_KEY" ] && echo "INFO: Anna's Archive full-text disabled (search-only mode)"
```

**Connectivity probe (run after install, host-agnostic):**

```
1. List active MCP servers (host-specific command).
   Expected: 9 servers — ai-scientist, mempalace, openalex, semanticscholar,
   arxiv, biorxiv, pubmed, annas-mcp, fetcher.
2. Run python <plugin>/mcp/server.py --selftest.
   Expected: prints "selftest: OK" with backend=sqlite_fts5.
3. Issue one tool call per MCP from the table above.
   Expected: 8/9 succeed (semanticscholar may skip if no key).
4. Report which MCPs failed and why; do not silently proceed.
```

---

## Universal install prompt (host-agnostic)

Paste this to any agent (Claude Code, Codex, Gemini CLI, Copilot CLI). The agent will detect its host environment and follow the right install path.

```
Install the ai-scientist plugin from https://github.com/danilkotelnikov/ai-scientist-plugin.

Steps:

1. Detect the host environment:
   - Claude Code: $CLAUDE_CODE_VERSION set or ~/.claude/ exists
   - Codex CLI: $CODEX_VERSION set or ~/.codex/ exists
   - Gemini CLI: $GEMINI_VERSION set or ~/.gemini/ exists

2. Read the appropriate install guide from the repo:
   - Claude Code: README.md (Quick Start section)
   - Codex CLI: .codex/INSTALL.md
   - Gemini CLI: .gemini/INSTALL.md

3. Execute the install steps verbatim. Stop and ask the user before any of:
   - destructive operations (rm -rf, force-overwrite)
   - operations that modify files outside ~/.{claude,codex,gemini}/, ~/.ai-scientist/, or the plugin install path
   - sudo / admin-elevation
   - operations that need credentials the user hasn't provided

4. After install, run the verification step from the host's INSTALL.md
   (typically: list MCP servers, check skill registration, run the
   plugin's --selftest).

5. Report back:
   - Which MCP servers were registered (expect 9: ai-scientist, mempalace,
     openalex, semanticscholar, arxiv, biorxiv, pubmed, annas-mcp, fetcher)
   - Which env vars are still unset (OPENALEX_EMAIL is required for the
     polite-pool throttle; SEMANTIC_SCHOLAR_KEY is optional but unblocks
     /search; ANNAS_* are optional for full-text)
   - Where the per-project MemPalace root was initialized
     (~/.ai-scientist/palace/)
   - Whether the AI-Scientist core MCP self-test passed

Do not install if you cannot verify the repository's README or LICENSE first.
```

---

## Codex install prompt (host-specific)

Use this when you're already in a Codex CLI session.

```
You are running in Codex CLI. Install the ai-scientist plugin from
https://github.com/danilkotelnikov/ai-scientist-plugin.

Run these steps in order. After each, briefly report the outcome.

Step 1 — Clone:
  git clone https://github.com/danilkotelnikov/ai-scientist-plugin.git \
    "$HOME/.codex/ai-scientist-plugin"
  (Windows: $env:USERPROFILE\.codex\ai-scientist-plugin)

Step 2 — Read the install guide:
  cat "$HOME/.codex/ai-scientist-plugin/.codex/INSTALL.md"
  Follow steps 2-9 of that guide verbatim.

Step 3 — Symlink skill + agents into ~/.agents/:
  Linux/macOS:
    mkdir -p ~/.agents/skills ~/.agents/agents
    ln -s ~/.codex/ai-scientist-plugin/plugins/ai-scientist/skills/ai-scientist \
      ~/.agents/skills/ai-scientist
    ln -s ~/.codex/ai-scientist-plugin/plugins/ai-scientist/agents \
      ~/.agents/agents/ai-scientist
  Windows (PowerShell):
    cmd /c mklink /J "$env:USERPROFILE\.agents\skills\ai-scientist" \
      "$env:USERPROFILE\.codex\ai-scientist-plugin\plugins\ai-scientist\skills\ai-scientist"
    cmd /c mklink /J "$env:USERPROFILE\.agents\agents\ai-scientist" \
      "$env:USERPROFILE\.codex\ai-scientist-plugin\plugins\ai-scientist\agents"

Step 4 — Append the Codex MCP config:
  Linux/macOS:
    cat ~/.codex/ai-scientist-plugin/plugins/ai-scientist/codex-config.toml.example \
      >> ~/.codex/config.toml
  Windows:
    Get-Content "$env:USERPROFILE\.codex\ai-scientist-plugin\plugins\ai-scientist\codex-config.toml.example" \
      | Add-Content "$env:USERPROFILE\.codex\config.toml"
  Stop here and ask the user to confirm the appended block.

Step 5 — Run the plugin install script (handles MemPalace pip-install,
clones JackKuo666/semanticscholar-MCP-Server and JackKuo666/bioRxiv-MCP-Server
to ~/.ai-scientist/external/, probes uvx and npx, runs the AI-Scientist
core MCP --selftest):
  Linux/macOS: bash ~/.codex/ai-scientist-plugin/plugins/ai-scientist/scripts/install.sh
  Windows:     powershell -File "$env:USERPROFILE\.codex\ai-scientist-plugin\plugins\ai-scientist\scripts\install.ps1"

Step 6 — Walk the per-MCP configuration checklist
(docs/AGENT_INSTALL_PROMPTS.md "Per-MCP configuration checklist" section):
  - For each of the 9 MCPs, verify install method completed and run the
    listed verification probe.
  - Specifically: ensure ~/.ai-scientist/external/semanticscholar-MCP-Server/
    and ~/.ai-scientist/external/bioRxiv-MCP-Server/ both exist with their
    entry .py files.
  - Probe env vars: warn (don't fail) on unset OPENALEX_EMAIL or
    SEMANTIC_SCHOLAR_KEY. Note ANNAS_* are optional.
  - For each MCP, issue one tool call (e.g. mcp__openalex__search_works
    with a tiny query) and report the result.

Step 7 — Restart Codex (codex restart) and verify connectivity:
  - Run "use ai-scientist to list jobs" — should hit /ai-scientist-list
  - List active MCP servers — expect 9 connected
  - Report which MCPs are red/yellow/green

If any step fails, surface the exact stderr to the user and ask before
retrying. Use Codex's spawn_agent worker pattern for the dispatch logic
described in plugins/ai-scientist/skills/ai-scientist/references/codex-tools.md.

Pin per-role models from the agents' codex: frontmatter blocks:
  - 5 heavy roles -> gpt-5.5, reasoning_effort=xhigh, max_output 128000,
    context 1050000
  - 7 light roles -> gpt-5.4, reasoning_effort=high, max_output 16384
```

---

## Gemini install prompt (host-specific)

Use this when you're in Gemini CLI.

```
You are running in Gemini CLI. Install the ai-scientist plugin from
https://github.com/danilkotelnikov/ai-scientist-plugin.

Run these steps in order. After each, briefly report the outcome.

Step 1 — Use the native extension installer:
  gemini extensions install https://github.com/danilkotelnikov/ai-scientist-plugin

  This clones to ~/.gemini/extensions/ai-scientist-plugin/ and reads the
  manifest at plugins/ai-scientist/gemini-extension.json. The manifest
  declares 9 MCP servers (ai-scientist, mempalace, openalex,
  semanticscholar, arxiv, biorxiv, pubmed, annas-mcp, fetcher).

Step 2 — Read the install guide:
  read_file ~/.gemini/extensions/ai-scientist-plugin/.gemini/INSTALL.md
  Follow steps 2-5 of that guide verbatim.

Step 3 — Run the plugin install script (handles MemPalace pip-install,
clones the two cloned-MCPs to ~/.ai-scientist/external/, probes uvx/npx,
runs the AI-Scientist core MCP --selftest):
  run_shell_command bash ~/.gemini/extensions/ai-scientist-plugin/plugins/ai-scientist/scripts/install.sh

Step 4 — Set env vars (ask the user for values, then persist via
save_memory to GEMINI.md so they survive restart):
  - OPENALEX_EMAIL          (required — without it, OpenAlex throttles to
                             1 req/s instead of 10 req/s polite pool)
  - SEMANTIC_SCHOLAR_KEY    (optional — unblocks Semantic Scholar /search;
                             without key, only /paper/{id} lookups work)
  - ANNAS_BASE_URL          (optional — needed for full-text downloads only)
  - ANNAS_DOWNLOAD_PATH     (optional — same)
  - ANNAS_SECRET_KEY        (optional — same)

Step 5 — Walk the per-MCP configuration checklist
(docs/AGENT_INSTALL_PROMPTS.md "Per-MCP configuration checklist"):
  - For each of the 9 MCPs, verify install method completed and run the
    listed verification probe (one tool call per MCP).
  - Specifically: ensure ~/.ai-scientist/external/semanticscholar-MCP-Server/
    and ~/.ai-scientist/external/bioRxiv-MCP-Server/ both exist.
  - Report status: green (works), yellow (works without optional env),
    red (failed install).

Step 6 — Restart Gemini and verify:
  - "activate skill ai-scientist"
  - "list ai-scientist jobs" (natural-language; Gemini doesn't have
    slash commands)
  - Confirm the 9 MCP servers show as connected

Read plugins/ai-scientist/skills/ai-scientist/references/gemini-tools.md
for the tool-name mapping (Task -> no equivalent; Read -> read_file;
TodoWrite -> write_todos; etc.) and the recommended session model:
  - For full pipelines: set session model to gemini-3.1-pro-preview
  - For partial intents (review-only, plot-only): gemini-3-flash-preview

Per-role models documented in each agent's gemini: frontmatter block,
but Gemini doesn't dispatch subagents — the session model handles every
phase inline. The pipeline still works; it just runs sequentially.
```

---

## Claude Code install prompt (host-specific)

Use this when you're in Claude Code.

```
You are running in Claude Code. Install the ai-scientist plugin from
https://github.com/danilkotelnikov/ai-scientist-plugin.

Run these slash commands in order:

  /plugin marketplace add danilkotelnikov/ai-scientist-plugin
  /plugin install ai-scientist@ai-scientist-plugin

After install, the plugin auto-registers:
  - 12 subagents in ~/.claude/plugins/.../agents/
  - 6 slash commands (/ai-scientist, /ai-scientist-list, etc.)
  - 9 MCP servers from mcp/.mcp.json
  - SessionStart / Stop / PreCompact hooks for MemPalace
  - The orchestrator skill

Then run the install script (handles pip install mempalace +
per-project palace init, clones JackKuo666/semanticscholar-MCP-Server
and JackKuo666/bioRxiv-MCP-Server to ~/.ai-scientist/external/,
probes uvx/npx, runs AI-Scientist core MCP --selftest):

  Windows:
    powershell -File "$env:USERPROFILE\.claude\plugins\cache\ai-scientist-plugin\ai-scientist\2.0.0\plugins\ai-scientist\scripts\install.ps1"

  Linux/macOS:
    bash ~/.claude/plugins/cache/ai-scientist-plugin/ai-scientist/2.0.0/plugins/ai-scientist/scripts/install.sh

Walk the per-MCP configuration checklist
(docs/AGENT_INSTALL_PROMPTS.md "Per-MCP configuration checklist"):
  - For each of the 9 MCPs, run the listed verification probe (one tool
    call per MCP from the checklist's last column).
  - Verify the two cloned MCPs (semanticscholar, biorxiv) live at:
      ~/.ai-scientist/external/semanticscholar-MCP-Server/semantic_scholar_server.py
      ~/.ai-scientist/external/bioRxiv-MCP-Server/biorxiv_server.py
  - Report which MCPs failed; do not silently proceed.

Verify with:
  /ai-scientist-list
  /mcp     (should list 9 servers: ai-scientist, mempalace,
            openalex, semanticscholar, arxiv, biorxiv, pubmed,
            annas-mcp, fetcher)

Set the required env vars (the install script prints warnings for any
unset ones):
  setx OPENALEX_EMAIL "your-email@example.com"           # Windows (required)
  export OPENALEX_EMAIL="your-email@example.com"          # Unix    (required)

Optional env vars (each one unlocks more functionality but isn't required
for basic operation):
  SEMANTIC_SCHOLAR_KEY      → unblocks Semantic Scholar /search endpoint
  ANNAS_BASE_URL            → switches Anna's Archive to a specific mirror
  ANNAS_DOWNLOAD_PATH       → enables full-text PDF downloads
  ANNAS_SECRET_KEY          → required for member-tier Anna's access

Per-role model pinning is automatic via the agents' frontmatter:
  - 5 heavy roles (ideator, hypothesizer, code-generator,
    manuscript-writer, reviewer) -> opus + thinking 48-64k
  - 7 light roles -> sonnet + thinking 8-16k
```

---

## How to source these prompts in agent configs

### Codex (`~/.codex/agents.toml` or `AGENTS.md`)

Add to the agent's instruction file:

```markdown
## Installing ai-scientist

When the user asks to install or set up the ai-scientist plugin, source
the prompt at:
  https://raw.githubusercontent.com/danilkotelnikov/ai-scientist-plugin/master/docs/AGENT_INSTALL_PROMPTS.md
Use the "Codex install prompt" section.
```

### Gemini (`~/.gemini/GEMINI.md`)

```markdown
@docs/AGENT_INSTALL_PROMPTS.md

When user requests "install ai-scientist", follow the "Gemini install prompt" section above.
```

(Use Gemini CLI's `@file` import syntax.)

### Claude Code (`~/.claude/CLAUDE.md`)

```markdown
## ai-scientist install

If the user asks to install or set up ai-scientist, follow the
"Claude Code install prompt" section in
~/.claude/plugins/cache/ai-scientist-plugin/ai-scientist/2.0.0/docs/AGENT_INSTALL_PROMPTS.md
(after the plugin is installed; otherwise fetch from the repo URL).
```

---

## Updating prompts

When a new host is added (e.g., Cursor, Copilot CLI), add a new section
above following the same template:

1. Self-contained prompt (no prior context)
2. Steps with explicit pause-and-confirm checkpoints for destructive ops
3. References to the host-specific install guide and tool-mapping reference
4. Verification step at the end
5. Per-role model pinning summary
