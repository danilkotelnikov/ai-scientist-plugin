# Installing AI-Scientist for Gemini CLI

Run the agentic-research pipeline inside Gemini CLI. Skills + agents + MCPs are bundled in a `gemini-extension.json` manifest — install via `gemini extensions install`.

## Prerequisites

- Gemini CLI ≥ 3.0
- Git
- Python 3.11+
- `uvx` (`pip install --user uv`)
- API access to `gemini-3.1-pro-preview` and `gemini-3-flash-preview` (or their stable 2.5 fallbacks)

## 1. Install via the Gemini extensions registry

```bash
gemini extensions install https://github.com/danilkotelnikov/ai-scientist-plugin
```

This clones the repo to `~/.gemini/extensions/ai-scientist/`, reads `gemini-extension.json` from `plugins/ai-scientist/`, and registers the 9 MCP servers + skills + agents.

## 2. Install the supporting Python package + literature MCPs

```bash
~/.gemini/extensions/ai-scientist-plugin/plugins/ai-scientist/scripts/install.sh
```

The script:
- pip-installs `mempalace` and the AI-Scientist core MCP requirements
- clones `JackKuo666/semanticscholar-MCP-Server` to `~/.ai-scientist/external/`
- probes `uvx` (for openalex/arxiv MCPs) and `npx` (for pubmed/annas/fetcher)
- runs `mempalace init ~/.ai-scientist/palace`
- runs the AI-Scientist MCP self-test

## 3. Set required env vars

```bash
export OPENALEX_EMAIL="your-email@example.com"
export SEMANTIC_SCHOLAR_KEY="your-key-from-semanticscholar.org"   # optional
export ANNAS_BASE_URL="annas-archive.gl"                          # optional
export ANNAS_DOWNLOAD_PATH="$HOME/Downloads/AA"                   # optional
export ANNAS_SECRET_KEY="your-key"                                # optional
```

Add to `~/.bashrc` / `~/.zshrc` / `~/.config/fish/config.fish` for persistence.

## 4. Restart Gemini CLI

```bash
gemini --restart
```

Gemini picks up the new skill, MCPs, and the extension manifest.

## 5. Verify

```
> activate skill ai-scientist
> use ai-scientist to research linear regression on synthetic data
```

## Caveat: no subagent support

Gemini CLI doesn't have `Task`/`spawn_agent`. The pipeline runs as a **single-session inline execution** — each phase's agent prompt is followed inline by the main session model.

**Recommendation:**
- Set Gemini's session model to `gemini-3.1-pro-preview` for full pipelines (heavy phases dominate).
- Use `gemini-3-flash-preview` for partial intents (review-only, plot-only, literature-only).

Per-phase model pinning is **documented in agent frontmatter under `gemini:` blocks** for the day Gemini CLI gains subagent support; for now, the session model handles all phases.

## Per-role recommended models

| Role group | Gemini model | Thinking | Output cap | Context |
|---|---|---|---|---|
| **Heavy** (ideator, hypothesizer, code-generator, manuscript-writer, reviewer) | `gemini-3.1-pro-preview` | `thinking_level: high` | 65,536 | 2,000,000 |
| **Light** (codebase-scanner, literature-searcher, experiment-runner, plotter, citator, meta-analyst) | `gemini-3-flash-preview` | `thinking_budget: 8192` | 8,192 | 1,000,000 |
| **Fixer** | `gemini-3-flash-preview` | `thinking_budget: 16384` | 16,384 | 1,000,000 |

## Updating

```bash
gemini extensions update ai-scientist
```

## Uninstalling

```bash
gemini extensions uninstall ai-scientist
```
