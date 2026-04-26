# AI-Scientist Plugin

End-to-end agentic research pipeline that runs across **Claude Code, Codex CLI, and Gemini CLI** with the same behavior on each. Literature search → ideation → hypothesis → experiment (single-shot or BFTS tree-search) → manuscript → peer review → visual figure validation.

**14 dedicated subagents**, each pinned per-host to a specific model with extended thinking. Auto-routes natural-language requests to the smallest agent subset.

## Highlights

- **Cross-host parity** — same skill, same agents, same MCPs on Claude Code, Codex, and Gemini CLI. Per-host model pinning written into each agent's frontmatter.
- **9 pre-configured MCP servers** auto-registered on install (knowledge store, MemPalace, OpenAlex, Semantic Scholar, arXiv, bioRxiv, PubMed, Anna's Archive, fetcher).
- **Per-project memory isolation** — MemPalace DB lives inside each job's output dir at `<output_dir>/.palace/`. No cross-project context can leak.
- **Dual-route operator** — every phase can run via the .md subagent (host-native, lightweight) OR via the canonical Sakana Python script bundled at `mcp/lib/sakana/` (upstream-faithful, benchmark-comparable). Pick per phase.
- **BFTS tree-search experiment runner** (canonical Sakana algorithm) — explores N implementation variants in parallel and picks the best by metric. Gated on `--bfts`.
- **VLM figure review** — duplicate detection, caption-content alignment, per-figure scoring 1–4 across clarity/relevance/quality.
- **LLM-driven install prompts** — copy-paste prompts at `docs/AGENT_INSTALL_PROMPTS.md` that any agent can follow to install the plugin end-to-end on any host.

## Quick start

### Claude Code

```
/plugin marketplace add danilkotelnikov/ai-scientist-plugin
/plugin install ai-scientist@ai-scientist-plugin
```

Then run the install script (handles MemPalace pip install, clones the two cloned MCPs, runs the core MCP self-test):

```powershell
# Windows
& "$env:USERPROFILE\.claude\plugins\cache\ai-scientist-plugin\ai-scientist\1.0.0\plugins\ai-scientist\scripts\install.ps1"
```

```bash
# Linux / macOS
bash ~/.claude/plugins/cache/ai-scientist-plugin/ai-scientist/1.0.0/plugins/ai-scientist/scripts/install.sh
```

After install, the plugin appears in **Customize** with toggles for each agent's model and the per-phase enable flags.

### Codex CLI

See `.codex/INSTALL.md` for the full 9-step setup. Summary:

```bash
git clone https://github.com/danilkotelnikov/ai-scientist-plugin.git ~/.codex/ai-scientist-plugin
ln -s ~/.codex/ai-scientist-plugin/plugins/ai-scientist/skills/ai-scientist ~/.agents/skills/ai-scientist
ln -s ~/.codex/ai-scientist-plugin/plugins/ai-scientist/agents              ~/.agents/agents/ai-scientist
cat ~/.codex/ai-scientist-plugin/plugins/ai-scientist/codex-config.toml.example >> ~/.codex/config.toml
bash ~/.codex/ai-scientist-plugin/plugins/ai-scientist/scripts/install.sh
codex restart
```

### Gemini CLI

See `.gemini/INSTALL.md` for the full setup. Summary:

```bash
gemini extensions install https://github.com/danilkotelnikov/ai-scientist-plugin
bash ~/.gemini/extensions/ai-scientist-plugin/plugins/ai-scientist/scripts/install.sh
gemini --restart
```

### Hand off install to your agent

If you'd rather have your agent install everything for you, paste the appropriate prompt from **[`docs/AGENT_INSTALL_PROMPTS.md`](docs/AGENT_INSTALL_PROMPTS.md)** to your Claude Code / Codex / Gemini session. Each prompt is self-contained and walks the per-MCP configuration checklist.

### Required env vars

```bash
export OPENALEX_EMAIL="your-email@example.com"           # required (polite-pool throttle)
export SEMANTIC_SCHOLAR_KEY="your-key"                    # optional (unlocks /search)
export ANNAS_BASE_URL="annas-archive.gl"                  # optional (full-text)
export ANNAS_DOWNLOAD_PATH="$HOME/Downloads/AA"           # optional (full-text)
export ANNAS_SECRET_KEY="your-key"                        # optional (full-text)
```

## Usage

```
/ai-scientist <topic>                                       # full pipeline
/ai-scientist <topic> --domain ml --codebase C:/repo        # full pipeline with codebase grounding
/ai-scientist <topic> --bfts                                # use BFTS tree-search experiment runner
/ai-scientist <topic> --use-canonical-scripts               # invoke upstream Sakana .py instead of .md agents
/ai-scientist-list                                          # list jobs
/ai-scientist-output <job-id>                               # fetch artifacts
/ai-scientist-query <terms>                                 # search persistent knowledge store
/ai-scientist-meta                                          # meta-analysis view
/ai-scientist-resume <job-id>                               # resume failed job
```

Natural-language invocations also work — the skill auto-routes to the right agent subset:

```
review my paper at C:/papers/draft.tex                      # → Reviewer only
review the figures in manuscript.pdf                        # → VLM Reviewer only
build plot for losses.npy                                   # → Plotter only
find papers on attention mechanisms                         # → LiteratureSearcher only
look at advanced NN algorithms and write code, then analyze # → Lit + CodeGen + Run + Plotter
compare RWKV vs Mamba experimentally                        # → CodeGen + Experiment + Plotter + Stats
```

## The 14 agents

### Per-host model pinning

Every agent declares its model in three frontmatter blocks (`model:` for Claude Code, `codex:` for Codex CLI, `gemini:` for Gemini CLI). The orchestrator picks the right block based on the host.

| # | Agent | Claude Code | Codex CLI | Gemini CLI |
|---|---|---|---|---|
| 1 | ideator | opus, 48k thinking | gpt-5.5 xhigh, 128k out, 1.05M ctx | gemini-3.1-pro-preview, level=high, 65k out, 2M ctx |
| 2 | codebase-scanner | sonnet, 8k | gpt-5.4 high, 16k out | gemini-3-flash-preview, budget=8k, 8k out, 1M ctx |
| 3 | literature-searcher | sonnet, 8k | gpt-5.4 high, 16k out | gemini-3-flash-preview, budget=8k, 8k out, 1M ctx |
| 4 | hypothesizer | opus, **64k** | gpt-5.5 xhigh, 128k out, 1.05M ctx | gemini-3.1-pro-preview, level=high, 65k out, 2M ctx |
| 5 | code-generator | opus, 48k | gpt-5.5 xhigh, 128k out, 1.05M ctx | gemini-3.1-pro-preview, level=high, 65k out, 2M ctx |
| 6 | experiment-runner | sonnet, 8k | gpt-5.4 high, 16k out | gemini-3-flash-preview, budget=8k, 8k out, 1M ctx |
| 7 | plotter | sonnet, 8k | gpt-5.4 high, 16k out | gemini-3-flash-preview, budget=8k, 8k out, 1M ctx |
| 8 | manuscript-writer | opus, 48k | gpt-5.5 xhigh, 128k out, 1.05M ctx | gemini-3.1-pro-preview, level=high, 65k out, 2M ctx |
| 9 | citator | sonnet, 8k | gpt-5.4 high, 16k out | gemini-3-flash-preview, budget=8k, 8k out, 1M ctx |
| 10 | reviewer | opus, **64k** | gpt-5.5 xhigh, 128k out, 1.05M ctx | gemini-3.1-pro-preview, level=high, 65k out, 2M ctx |
| 11 | meta-analyst | sonnet, 8k | gpt-5.4 high, 16k out | gemini-3-flash-preview, budget=8k, 8k out, 1M ctx |
| 12 | fixer | sonnet, 16k | gpt-5.4 high, 24k out | gemini-3-flash-preview, budget=16k, 16k out, 1M ctx |
| 13 | **vlm-reviewer** | opus, 48k | gpt-5.5 high, 65k out | gemini-3.1-pro-preview, level=high, 32k out, 2M ctx |
| 14 | **tree-search-runner** | opus, **64k** | gpt-5.5 xhigh, 65k out | gemini-3.1-pro-preview, level=high, 32k out, 2M ctx |

### Pipeline phases

| Phase | Agent | Bundled canonical .py |
|---|---|---|
| -1 Intent classification | (skill) | — |
| 0 Init | (skill) — creates per-project palace at `<output_dir>/.palace/` | — |
| 0.5 Ideation | ideator | `mcp/lib/sakana/perform_ideation_temp_free.py` |
| 0.75 Codebase scan | codebase-scanner | — |
| 1 Literature search | literature-searcher (×6 parallel: openalex, arxiv, pubmed, biorxiv, semanticscholar, annas) | — |
| 2 Hypothesis | hypothesizer | — |
| 3 Codegen | code-generator | — |
| 4a Experiment (single-shot) | experiment-runner | — |
| 4b Experiment (BFTS) | tree-search-runner | `mcp/lib/sakana/treesearch/perform_experiments_bfts_with_agentmanager.py` |
| 5.5 Plot aggregation | plotter | `mcp/lib/sakana/perform_plotting.py` |
| 5 Manuscript | manuscript-writer (with 6 nested section subagents) | `mcp/lib/sakana/perform_writeup.py` (NeurIPS) / `perform_icbinb_writeup.py` (workshop) |
| 6 Citation enrichment | citator | — |
| 7 Self-review (textual) | reviewer | `mcp/lib/sakana/perform_llm_review.py` |
| 8 LaTeX compile | (skill) | — |
| 8.25 Word export | (skill — pandoc, falls back to anthropic-skills:docx) | — |
| 8.5 VLM figure review | vlm-reviewer | `mcp/lib/sakana/perform_vlm_review.py` |
| 9 Knowledge indexing | (skill — direct MCP) | — |
| 10 Meta-analysis | meta-analyst | — |
| F Fixer (on any failure) | fixer | — |

## 9 pre-configured MCP servers

| MCP | Source | Purpose |
|---|---|---|
| `ai-scientist` | bundled in plugin | Knowledge store (SQLite + ChromaDB), codebase analyzer, meta-analysis |
| `mempalace` | [MemPalace/mempalace](https://github.com/MemPalace/mempalace) | Per-project memory DB with auto-save hooks |
| `openalex` | [drAbreu/alex-mcp](https://github.com/drAbreu/alex-mcp) | 240M+ scholarly works |
| `semanticscholar` | [JackKuo666/semanticscholar-MCP-Server](https://github.com/JackKuo666/semanticscholar-MCP-Server) | Semantic Scholar full API |
| `arxiv` | `arxiv-mcp-server` (PyPI via uvx) | Preprints (CS/physics/math/bio) |
| `biorxiv` | [JackKuo666/bioRxiv-MCP-Server](https://github.com/JackKuo666/bioRxiv-MCP-Server) | Life-sciences preprints |
| `pubmed` | `pubmed-mcp` (npm via npx) | Biomedical literature |
| `annas-mcp` | `annas-mcp` (npm via npx) | Anna's Archive full-text |
| `fetcher` | `fetcher-mcp` (npm via npx) | HTTP fallback for Consensus + Crossref |

The install script auto-installs all of these. See **[Per-MCP configuration checklist](docs/AGENT_INSTALL_PROMPTS.md#per-mcp-configuration-checklist-referenced-by-every-install-prompt)** for env-var requirements and verification probes.

## Memory model — per-project, no cross-project leakage

Two layers:

| Layer | Path | Lifetime | What's stored |
|---|---|---|---|
| **Cross-job global knowledge** | `~/.ai-scientist/knowledge.db` (SQLite + ChromaDB) | All jobs forever | Papers (deduped), hypotheses, benchmark outcomes, claims, knowledge graph triples, trajectories |
| **Per-project palace** | `<output_dir>/.palace/` | One project | Wings → rooms → drawers (full conversation context, agent diaries, intermediate states). Lives INSIDE the job dir — deleting the project removes the palace |

**Strict isolation guarantee**: every agent's prompt includes the universal MemPalace contract — call `mcp__mempalace__wake_up(root="<output_dir>/.palace", ...)` on entry, `mcp__mempalace__mine(root="<output_dir>/.palace", ...)` on exit. Agents never read or write any other palace path.

**Auto-save lifecycle** (no manual calls needed):
- **SessionStart hook** (`hooks/mempalace-recall.sh`) — emits 4k-token wake-up summary on session resume.
- **PreCompact hook** (`hooks/mempalace-save.sh precompact`) — mines in-flight conversation before context is compacted.
- **Stop hook** (`hooks/mempalace-save.sh stop`) — final save on agent exit.

## Templates

| Type | Bundled at | Templates |
|---|---|---|
| LaTeX | `mcp/templates/latex/` | aiscientist-default, overleaf-minimal, elsevier-cas-sc, ieee-conference, acm-sig, **icml-2025** (canonical Sakana), **icbinb** (workshop) |
| Word | `mcp/templates/word/` | arxiv-shared-1, minimalist, two-column-academic |
| Few-shot examples | `mcp/templates/fewshot/` | attention.{pdf,json,txt}, carpe_diem, automated_relational |
| Idea seeds | `mcp/templates/ideas/` | i_cant_believe_its_not_better.{json,md,py} |

Visual validation pass on rendered PNGs (Phase 8.5) — vlm-reviewer agent reads images directly via multimodal Read.

## Tweaking

User overrides go in `~/.claude/settings.json` (Claude Code) / `~/.codex/config.toml` (Codex) / `~/.gemini/settings.json` (Gemini):

```json
{
  "plugins": {
    "ai-scientist": {
      "agents": {
        "reviewer": { "model": "sonnet", "thinking_budget": 32000 }
      },
      "codex_agents": {
        "reviewer": { "model": "gpt-5.4", "reasoning_effort": "high", "max_output_tokens": 32768 }
      },
      "gemini_agents": {
        "reviewer": { "model": "gemini-2.5-pro", "thinking_budget": 24576, "max_output_tokens": 16384, "context_window": 2000000 }
      },
      "interactivity": "full",
      "literature": { "max_papers": 30 },
      "experiment": { "use_bfts": true, "bfts_time_budget_minutes": 60 },
      "memory": { "scope": "project", "isolation": "strict" }
    }
  }
}
```

Full schema at [`plugins/ai-scientist/settings/settings.schema.json`](plugins/ai-scientist/settings/settings.schema.json).

## Architecture

```
plugins/ai-scientist/
├── agents/                    # 14 dedicated subagents (each with claude / codex / gemini frontmatter blocks)
├── skills/ai-scientist/
│   ├── SKILL.md               # orchestrator (intent routing + dispatch + universal MemPalace contract)
│   ├── domain-templates.md    # 6 domain configs (ml, optimization, statistical, mathematical, comp_bio, sw_eng)
│   ├── academic-domains.md    # trusted publisher allowlist
│   ├── search-queries.md      # 8-query strategy
│   ├── routing-intents.md     # 12 named intents
│   └── references/
│       ├── codex-tools.md     # Task → spawn_agent, TodoWrite → update_plan, etc.
│       └── gemini-tools.md    # Read → read_file, Skill → activate_skill, etc.
├── commands/                  # 6 slash commands (Claude Code)
├── mcp/
│   ├── server.py              # plugin's core MCP (knowledge store, codebase analyzer, meta-analysis)
│   ├── lib/                   # core MCP support modules
│   ├── lib/sakana/            # canonical Sakana AI-Scientist Python (~10,200 LOC, 33 .py files)
│   │   ├── llm.py + vlm.py
│   │   ├── perform_*.py       # ideation, writeup, icbinb_writeup, llm_review, vlm_review, plotting
│   │   ├── treesearch/        # BFTS (11 files, 5,335 LOC)
│   │   ├── tools/             # semantic_scholar, base_tool
│   │   └── bfts_config.yaml
│   ├── scripts/               # migrate_jsonl_to_sqlite.py, index_chroma.py
│   └── templates/             # latex/ + word/ + fewshot/ + ideas/
├── hooks/                     # mempalace-recall.sh, mempalace-save.sh, hooks.json
├── settings/                  # default-settings.json + settings.schema.json
├── scripts/                   # install.ps1, install.sh, migrate-from-skill.ps1, rollback.ps1, verify.ps1
├── tests/                     # 129 passing tests (static + routing + per-host frontmatter)
├── codex-config.toml.example  # copy-paste TOML for ~/.codex/config.toml
├── gemini-extension.json      # Gemini CLI extension manifest
└── .claude-plugin/            # Claude Code plugin manifest + marketplace
```

Plus at the repo root:

- `.codex/INSTALL.md` — Codex CLI install guide
- `.gemini/INSTALL.md` — Gemini CLI install guide
- `docs/AGENT_INSTALL_PROMPTS.md` — copy-paste prompts for any agent to install the plugin
- `docs/specs/` + `docs/plans/` — original design spec and implementation plan

## Cross-host install summary

| Host | One-liner |
|---|---|
| Claude Code | `/plugin marketplace add danilkotelnikov/ai-scientist-plugin && /plugin install ai-scientist@ai-scientist-plugin` |
| Codex CLI | clone + symlink + `cat codex-config.toml.example >> ~/.codex/config.toml` (see `.codex/INSTALL.md`) |
| Gemini CLI | `gemini extensions install https://github.com/danilkotelnikov/ai-scientist-plugin` |
| LLM-driven | paste from `docs/AGENT_INSTALL_PROMPTS.md` to your agent |

## Tests

129 tests pass (static frontmatter checks for all 14 agents across all 3 hosts, routing fixtures, schema validation, MCP self-test).

```bash
cd plugins/ai-scientist && python -m pytest tests/
python plugins/ai-scientist/mcp/server.py --selftest
```

## Spec & plan

- Design: [`docs/specs/2026-04-25-ai-scientist-plugin-design.md`](docs/specs/2026-04-25-ai-scientist-plugin-design.md)
- Implementation plan: [`docs/plans/2026-04-25-ai-scientist-plugin-implementation.md`](docs/plans/2026-04-25-ai-scientist-plugin-implementation.md)

## Credits

- **Sakana AI's AI-Scientist** ([github.com/SakanaAI/AI-Scientist-v2](https://github.com/SakanaAI/AI-Scientist-v2), MIT) — canonical Python pipeline (BFTS, perform_writeup, perform_vlm_review, perform_llm_review, perform_plotting). Bundled at `mcp/lib/sakana/`.
- **MemPalace** ([github.com/MemPalace/mempalace](https://github.com/MemPalace/mempalace), MIT) — per-project memory DB.
- **drAbreu/alex-mcp** — OpenAlex MCP wrapper.
- **JackKuo666/semanticscholar-MCP-Server** + **JackKuo666/bioRxiv-MCP-Server** — Semantic Scholar and bioRxiv MCP wrappers.

## License

MIT — see [LICENSE](LICENSE).
