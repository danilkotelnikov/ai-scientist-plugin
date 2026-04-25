# Codex Tool Mapping

The orchestrator skill (`SKILL.md`) and the 12 agent prompts use Claude Code tool names because that's the primary host. When running inside Codex, translate as follows.

## Core tool mapping

| Skill / agent references | Codex equivalent |
|---|---|
| `Task(subagent_type="...", prompt=...)` | `spawn_agent(agent_type="worker", message=<filled prompt>)` |
| Multiple `Task(...)` calls in one message (parallel dispatch) | Multiple `spawn_agent(...)` calls in one message, then `wait` to collect results |
| `Task` returns result | `wait` |
| `Task` completes automatically | `close_agent` to free the worker slot |
| `TodoWrite([...])` (task tracking) | `update_plan(...)` |
| `Skill(skill="anthropic-skills:docx", ...)` | Skills load natively in Codex — invoke inline by referencing the skill name |
| `AskUserQuestion(questions=[...])` | Inline prompt to the user — phrase as "I need to confirm: ..." |
| `Read`, `Write`, `Edit` | Native file tools |
| `Bash` | Native shell tool |
| `Glob`, `Grep` | Native search tools (or `rg` via shell) |
| `WebFetch` | **Not available** — use `mcp__fetcher__fetch_url` (already in literature-searcher's tools) or Bash + `curl` |

## Multi-agent feature

Codex requires this in `~/.codex/config.toml` to enable `spawn_agent`:

```toml
[features]
multi_agent = true
```

Without it, the orchestrator falls back to sequential phase execution (slower but functional — each phase becomes an inline reasoning pass instead of a worker dispatch).

## Named-agent dispatch in Codex

Codex doesn't have a named-agent registry like Claude Code's `subagent_type="ai-scientist-ideator"`. The orchestrator must:

1. Read the agent's `.md` file from `~/.agents/agents/ai-scientist/<agent-name>.md` (symlinked at install).
2. Strip the YAML frontmatter (the `model:`, `thinking:`, `tools:` block).
3. Substitute the `<input name="...">` placeholders with the actual values.
4. Call `spawn_agent(agent_type="worker", message=<filled body>)`.

### Recommended message framing

```
Your task is to perform the following. Follow the instructions below exactly.

<agent-instructions>
[stripped + filled body of the agent's .md file]
</agent-instructions>

Inputs:
<input name="topic">linear regression on synthetic data</input>
<input name="domain">statistical</input>
... (etc, one per declared input)

Execute this now. Output ONLY the structured response wrapped in <output name="..."> tags as specified in the instructions above. No prose outside the tags.
```

- Use task-delegation framing ("Your task is...") not persona framing ("You are...")
- Wrap instructions in `<agent-instructions>` XML tags so the model treats them as authoritative
- End with an explicit execution directive to prevent the worker from summarizing the instructions back

## Model pinning

The agent frontmatter declares `model: opus` or `model: sonnet` and a `thinking.budget_tokens` value. Codex's `spawn_agent` accepts a `model_override` and `thinking_budget` parameter (when supported). Read these from the agent's frontmatter when dispatching:

```python
# Pseudocode — actual call shape depends on Codex version
import yaml, re
agent_file = read("~/.agents/agents/ai-scientist/ideator.md")
match = re.match(r"^---\n(.*?)\n---", agent_file, re.DOTALL)
fm = yaml.safe_load(match.group(1))
body = agent_file[match.end():]

spawn_agent(
    agent_type="worker",
    message=fill_inputs(body, inputs),
    model_override=fm["model"],          # "opus" | "sonnet"
    thinking_budget=fm["thinking"]["budget_tokens"],  # 8000 | 48000 | 64000
)
```

If `model_override` / `thinking_budget` aren't supported in your Codex version, the worker uses the session's default model. The agents are still functional, just without per-role specialization.

## MCP server access

Codex's `[mcp_servers.<name>]` config blocks register tool prefixes — once added to `~/.codex/config.toml` (see `.codex/INSTALL.md` step 5), the agents call:

| MCP | Tool example |
|---|---|
| `ai-scientist` | `mcp__ai-scientist__search_knowledge_index` |
| `openalex` | `mcp__openalex__search_works` |
| `semanticscholar` | `mcp__semanticscholar__search_semantic_scholar` |
| Pre-existing platform MCPs (arxiv, biorxiv, pubmed, annas-mcp, fetcher) | Already registered in your Codex config |

The MCP tool names are identical to Claude Code's — Codex uses the same `mcp__<server>__<tool>` namespace. No translation needed.

## Slash commands

Codex doesn't implement slash commands. The skill activates via natural-language phrasing instead:

| Claude Code | Codex equivalent |
|---|---|
| `/ai-scientist <topic>` | "use ai-scientist to research \<topic\>" or "/ai-scientist \<topic\>" (Codex's skill matcher handles both) |
| `/ai-scientist-list` | "list ai-scientist jobs" |
| `/ai-scientist-output <id>` | "show output for ai-scientist job \<id\>" |
| `/ai-scientist-query <terms>` | "search ai-scientist knowledge for \<terms\>" |
| `/ai-scientist-meta` | "show ai-scientist meta-analysis" |
| `/ai-scientist-resume <id>` | "resume ai-scientist job \<id\>" |

## Environment detection

The orchestrator can detect Codex vs. Claude Code at runtime:

```bash
if [ -n "$CODEX_VERSION" ] || [ -d "$HOME/.codex" ]; then
    echo "Codex"
else
    echo "Claude Code"
fi
```

Or in Python:

```python
import os
host = "codex" if os.environ.get("CODEX_VERSION") or os.path.isdir(os.path.expanduser("~/.codex")) else "claude_code"
```

The skill body is host-agnostic; only tool calls need translation, and that's documented above.
