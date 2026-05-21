# Gemini CLI Tool Mapping

The orchestrator skill (`SKILL.md`) and the 12 agent prompts use Claude Code tool names. When running inside Gemini CLI, translate as follows.

## Core tool mapping

| Skill / agent references | Gemini CLI equivalent |
|---|---|
| `Read` | `read_file` |
| `Write` | `write_file` |
| `Edit` | `replace` |
| `Bash` | `run_shell_command` |
| `Grep` | `grep_search` |
| `Glob` | `glob` |
| `TodoWrite` | `write_todos` (or `tracker_create_task` for richer tracking) |
| `WebFetch` | `web_fetch` |
| `WebSearch` | `google_web_search` |
| `Skill(skill="...")` | `activate_skill` |
| `AskUserQuestion` | `ask_user` |
| `Task(subagent_type="...")` | **No native equivalent** — see "No subagent support" below |

## No subagent support

Gemini CLI does not implement Task/spawn_agent dispatch. The pipeline falls back to **single-session inline execution** of each phase. This means:

- The orchestrator skill executes Phase 0 → 0.5 → 1 → 2 → ... → 10 sequentially in the same conversation context.
- Each phase's agent prompt (from `agents/<name>.md`) is inlined as a sub-prompt to the main session — the main model becomes "the agent" for the duration of that phase.
- **Per-phase model pinning is not enforceable** in Gemini CLI as of v3.x — the session model is fixed at start. The `gemini:` frontmatter values document the *recommended* model per role; the user picks one model for the whole session.
- **Recommended pick** when running on Gemini: `gemini-3.1-pro-preview` for full pipelines (heavy phases dominate cost), `gemini-3-flash-preview` for partial intents (review-only, plot-only, lit-only).

When `Task` is referenced in skill/agent prompts under Gemini, treat it as: "perform the phase's work yourself in this same conversation, following the prompt content from the named agent file."

## Parallel literature search workaround

The orchestrator's Phase 1 dispatches 6 parallel literature-searcher Tasks in Claude Code. Under Gemini, this becomes a sequential loop:

1. For each enabled source in `literature.sources`:
   - Read `agents/literature-searcher.md`, fill `<input name="source">` with the current source.
   - Execute the steps inline.
   - Append the returned paper list to a merged array.
2. Dedup, sort, write `paper_list.json`.

Wall-clock will be longer (sum of per-source times instead of max), but the workflow still completes.

## Thinking-mode parameter

Gemini 3.x Pro Preview uses `thinking_level` (categorical: low/medium/high) — the agent frontmatter sets `thinking_level: high` for heavy roles.

Gemini 3 Flash Preview and Gemini 2.5 series use `thinking_budget` (numeric, 0–32768 for 2.5 Pro, 0–24576 for Flash/Flash-Lite). The frontmatter sets `thinking_budget: 8192` for light roles, `16384` for fixer.

Pseudocode for using these in a Gemini API call:

```python
from google import genai
from google.genai import types

# For Gemini 3.x Pro (uses thinking_level)
client.models.generate_content(
    model="gemini-3.1-pro-preview",
    contents=prompt,
    config=types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_level="high"),
        max_output_tokens=65536,
    ),
)

# For Gemini 3 Flash / 2.5 series (uses thinking_budget)
client.models.generate_content(
    model="gemini-3-flash-preview",
    contents=prompt,
    config=types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_budget=8192),
        max_output_tokens=8192,
    ),
)
```

## MCP server access

Gemini CLI extensions declare MCP servers in `gemini-extension.json` under `mcpServers` — same shape as Claude Code's `.mcp.json`. The plugin's `gemini-extension.json` registers all 9 servers (ai-scientist, mempalace, openalex, semanticscholar, arxiv, biorxiv, pubmed, annas-mcp, fetcher). Tool names are identical to Claude Code: `mcp__<server>__<tool>`.

## Slash commands

Gemini commands are TOML files in `commands/`. The plugin's slash commands (`/ai-scientist`, `/ai-scientist-list`, etc.) live in `plugins/ai-scientist/commands/` as Markdown — Gemini doesn't auto-detect them. Use natural-language activation instead:

| Claude Code slash command | Gemini equivalent (natural language) |
|---|---|
| `/ai-scientist <topic>` | "use ai-scientist to research \<topic\>" |
| `/ai-scientist-list` | "list ai-scientist jobs" |
| `/ai-scientist-output <id>` | "show output for ai-scientist job \<id\>" |
| `/ai-scientist-query <terms>` | "search ai-scientist knowledge for \<terms\>" |
| `/ai-scientist-meta` | "show ai-scientist meta-analysis" |
| `/ai-scientist-resume <id>` | "resume ai-scientist job \<id\>" |

Or paste a manifest of available commands at session start so Gemini's skill activation routes correctly.

## Environment detection

```bash
if [ -n "$GEMINI_VERSION" ] || [ -d "$HOME/.gemini" ]; then
    echo "Gemini CLI"
fi
```

```python
import os
host = "gemini" if (os.environ.get("GEMINI_VERSION") or os.path.isdir(os.path.expanduser("~/.gemini"))) else None
```
