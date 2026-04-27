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

Add to `~/.codex/config.toml`:

```toml
[features]
multi_agent = true
```

This unlocks `spawn_agent`, `wait`, and `close_agent` — required for the orchestrator to dispatch the 16 dedicated subagents in parallel.

## 5. Register the bundled MCP servers (9 total)

Append to `~/.codex/config.toml`. The full block is at `<plugin>/plugins/ai-scientist/codex-config.toml.example` — copy-paste ready. Servers registered:

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
