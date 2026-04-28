# Installing AI-Scientist for Codex

Run the same agentic-research pipeline inside the Codex CLI. Skills are discovered natively; subagents (Ideator, Hypothesizer, Reviewer, etc.) are dispatched via Codex's `spawn_agent` worker pattern; the OpenAlex / Semantic Scholar / ai-scientist MCPs all run side-by-side via Codex's `[mcp_servers]` config blocks.

## Prerequisites

- Codex CLI ≥ 1.0
- Git
- Python 3.11+
- `uvx` (`pip install --user uv` or `winget install astral-sh.uv`)

## 1. Clone the plugin to a stable path

**Linux / macOS:**

```bash
git clone https://github.com/danilkotelnikov/ai-scientist-plugin.git ~/.codex/ai-scientist-plugin
```

**Windows (PowerShell):**

```powershell
git clone https://github.com/danilkotelnikov/ai-scientist-plugin.git "$env:USERPROFILE\.codex\ai-scientist-plugin"
```

## 2. Symlink the skill directory

Codex discovers skills via `~/.agents/skills/<name>`. The plugin's skill lives at `plugins/ai-scientist/skills/`.

**Linux / macOS:**

```bash
mkdir -p ~/.agents/skills
ln -s ~/.codex/ai-scientist-plugin/plugins/ai-scientist/skills/ai-scientist ~/.agents/skills/ai-scientist
```

**Windows (PowerShell, junction since `ln -s` needs admin):**

```powershell
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.agents\skills"
cmd /c mklink /J "$env:USERPROFILE\.agents\skills\ai-scientist" "$env:USERPROFILE\.codex\ai-scientist-plugin\plugins\ai-scientist\skills\ai-scientist"
```

## 3. Symlink the agents directory (subagent dispatch)

Each phase agent (`ideator.md`, `hypothesizer.md`, etc.) is a prompt template Codex dispatches via `spawn_agent`. Symlink the `agents/` dir so the skill can find them.

**Linux / macOS:**

```bash
mkdir -p ~/.agents/agents
ln -s ~/.codex/ai-scientist-plugin/plugins/ai-scientist/agents ~/.agents/agents/ai-scientist
```

**Windows:**

```powershell
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.agents\agents"
cmd /c mklink /J "$env:USERPROFILE\.agents\agents\ai-scientist" "$env:USERPROFILE\.codex\ai-scientist-plugin\plugins\ai-scientist\agents"
```

## 4. Enable multi-agent dispatch

The v2.1 reviewer phase uses Codex `spawn_agent` waves. Add (or confirm) in `~/.codex/config.toml`:

```toml
[features]
multi_agent = true

[agents]
max_threads = 6
max_depth = 1
```

`multi_agent = true` unlocks `spawn_agent`, `wait`, `close_agent`, `send_input`, `resume_agent`. `max_threads = 6` is the default cap and is enough for the 3-bias reviewer fan-out plus one buffer slot.

**Critical:** the v2.1 dispatcher always calls `close_agent` after every `spawn_agent` wave to defeat the slot-leak bug ([codex issue #18335](https://github.com/openai/codex/issues/18335)). If you observe spawn slots leaking between turns, file an upstream bug; the plugin already does the right thing on its end.

## 5. Register the bundled MCP servers (9 total)

Append to `~/.codex/config.toml`. The full block is at `<plugin>/plugins/ai-scientist/codex-config.toml.example` -- copy-paste ready.

> **Pre-flight on `[features]`:** the example file deliberately omits its own `[features]` table because TOML forbids two sections with the same name and most installs already have one. Step 4 above told you to ensure `multi_agent = true` lives under your existing `[features]` block. If you're appending to a config that lacks `[features]` entirely, add it yourself (anywhere in the file) with that single key. **If you previously appended an older copy of this example that included `[features]`, deduplicate it before running `codex restart`** -- otherwise Codex will refuse to load the file with a `duplicate key` error.
>
> **Pre-flight on `[mcp_servers.*]`:** the example registers 9 MCP servers (`ai-scientist`, `mempalace`, `openalex`, `semanticscholar`, `arxiv`, `biorxiv`, `pubmed`, `annas-mcp`, `fetcher`). If your existing `~/.codex/config.toml` already registers any of those exact names (from a previous install of this plugin or any other MCP using the same name), the append will produce TOML duplicate-table errors. Grep first:
>
> ```bash
> grep -E '^\[mcp_servers\.(ai-scientist|mempalace|openalex|semanticscholar|arxiv|biorxiv|pubmed|annas-mcp|fetcher)\]' ~/.codex/config.toml
> ```
>
> For every match, either delete the older block from your config OR skip the matching block from the example when copying. **Do not paste both.** If you already pasted both and `codex restart` is failing with `duplicate key`, find the most recent appended block in your config (usually after a comment header reading `Append the contents of this file...`) and delete from that header to EOF, then re-merge selectively.
>
> **Encoding gotcha on Windows:** if you edit the file with `Set-Content -Encoding UTF8` (PowerShell 5.1) it adds a UTF-8 BOM that Codex's TOML parser rejects with "Invalid statement at line 1 column 1". Either use `Add-Content` (which preserves the existing encoding) or use `Out-File` with `-Encoding utf8NoBOM` (PowerShell 6+) / `[System.IO.File]::WriteAllText($path, $text, [System.Text.UTF8Encoding]::new($false))` (5.1). Servers registered:

| Server | Purpose |
|---|---|
| `ai-scientist` | Plugin's core MCP — knowledge store, codebase analyzer, meta-analysis |
| `mempalace` | Per-project memory DB; auto-saves before context compaction |
| `openalex` | drAbreu/alex-mcp v4.1.0 — 240M+ scholarly works |
| `semanticscholar` | JackKuo666/semanticscholar-MCP-Server — Semantic Scholar full API |
| `arxiv` | arxiv-mcp-server — preprints (CS/physics/math/bio) |
| `biorxiv` | bioRxiv MCP — life-sciences preprints |
| `pubmed` | pubmed-mcp — biomedical literature |
| `annas-mcp` | Anna's Archive — full-text article access |
| `fetcher` | Generic HTTP-fetch fallback (Consensus, Crossref, etc.) |

(Substitute your email and Semantic Scholar key. The `${env:VAR}` syntax is Codex-native.)

**Easiest:**

```bash
# Linux / macOS
cat ~/.codex/ai-scientist-plugin/plugins/ai-scientist/codex-config.toml.example >> ~/.codex/config.toml
```

```powershell
# Windows
Get-Content "$env:USERPROFILE\.codex\ai-scientist-plugin\plugins\ai-scientist\codex-config.toml.example" | Add-Content "$env:USERPROFILE\.codex\config.toml"
```

(On Linux/macOS edit the example first to replace `${env:USERPROFILE}` with `${env:HOME}` before appending.)

The example file declares **`[features] multi_agent = true`** and all 9 MCP-server blocks. Open it before appending to skim what gets registered.

## 5b. (recommended) Add the OpenAI Docs MCP

For grounding any Codex-API or subagent-API claim against official documentation rather than memorized state:

```powershell
codex mcp add openaiDeveloperDocs --url https://developers.openai.com/mcp
codex mcp list
```

The plugin's preflight (`preflight.probe_memory_tools`) will detect this server and write `tool_preflight.json` showing whether `search_openai_docs` / `fetch_openai_doc` are available. The pipeline can then ground its OpenAI-API claims against the live docs.

If you skip this, all preflight reports will record `official_docs_mcp.available = false` and the workflow falls back to fetching official OpenAI web pages directly.

## 6. Run the install script

The install script handles: pip-install of the AI-Scientist core MCP requirements, clone of the Semantic Scholar MCP repo to `~/.ai-scientist/external/`, plus probing pandoc/libreoffice/pdflatex/pdftoppm.

**Linux / macOS:**

```bash
~/.codex/ai-scientist-plugin/plugins/ai-scientist/scripts/install.sh
```

**Windows (PowerShell):**

```powershell
& "$env:USERPROFILE\.codex\ai-scientist-plugin\plugins\ai-scientist\scripts\install.ps1"
```

## 7. Set required env vars

```bash
# Linux / macOS
export OPENALEX_EMAIL="your-email@example.com"
export SEMANTIC_SCHOLAR_KEY="your-key-from-semanticscholar.org"   # optional but unblocks /search
```

```powershell
# Windows
setx OPENALEX_EMAIL "your-email@example.com"
setx SEMANTIC_SCHOLAR_KEY "your-key-from-semanticscholar.org"
```

## 8. Restart Codex

```bash
codex restart        # or: quit and relaunch the CLI
```

Codex picks up the new skill, agents, and MCP servers.

## 9. Verify

In Codex:

```
> use the ai-scientist skill to research linear regression on synthetic data
```

Or invoke directly:

```
> /ai-scientist linear regression on synthetic data --domain statistical
```

(Codex translates Claude-Code-style `/ai-scientist` invocations into the underlying skill activation.)

## Tool-name mapping

The skill's prompts reference Claude Code tool names. Codex maps them automatically via the reference at `plugins/ai-scientist/skills/ai-scientist/references/codex-tools.md`:

| Claude Code | Codex |
|---|---|
| `Task` (dispatch subagent) | `spawn_agent` |
| Multiple `Task` calls in parallel | Multiple `spawn_agent` calls + `wait` |
| `TodoWrite` | `update_plan` |
| `AskUserQuestion` | Codex inline prompt |
| `Skill` tool | Skills load natively — follow instructions inline |
| `Read`, `Write`, `Edit`, `Bash` | Native equivalents |

## Updating

```bash
cd ~/.codex/ai-scientist-plugin && git pull
```

## Uninstalling

```bash
rm ~/.agents/skills/ai-scientist
rm ~/.agents/agents/ai-scientist
# Remove the [mcp_servers.ai-scientist], [mcp_servers.openalex], [mcp_servers.semanticscholar] blocks from ~/.codex/config.toml
rm -rf ~/.codex/ai-scientist-plugin
```

(Optionally also `rm -rf ~/.ai-scientist/` to drop the knowledge store. Leave it if you want to preserve it for reinstall.)
