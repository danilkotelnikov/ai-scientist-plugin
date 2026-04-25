# AI-Scientist Claude Code Plugin

End-to-end agentic research pipeline: literature search → hypothesis → experiment → manuscript → peer review. **12 dedicated subagents**, each on a pinned model with extended thinking. Auto-routes natural-language requests ("review X", "plot Y", "code Z") to the smallest agent subset.

## Quick start (Windows)

```powershell
# 1. Install plugin dependencies (probes pandoc/libreoffice/pdflatex, runs MCP selftest)
.\scripts\install.ps1

# 2. Migrate from old skill (one-time, archives ~/.claude/skills/ai-scientist to ~/.claude/backups/)
.\scripts\migrate-from-skill.ps1
```

Inside Claude Code:

```
/plugin marketplace add danilkotelnikov/ai-scientist-plugin
/plugin install ai-scientist@ai-scientist-plugin
```

After install, the plugin appears in **Customize** with toggles for each agent's model and the per-phase enable flags.

(For local-only install without GitHub, use `/plugin marketplace add ./ai-scientist-plugin` from the parent directory containing the plugin folder.)

```powershell
# 3. Verify
.\scripts\verify.ps1
```

## Usage

```
/ai-scientist <topic>                                       # full pipeline
/ai-scientist <topic> --domain ml --codebase C:/repo        # full pipeline with codebase grounding
/ai-scientist-list                                          # list jobs
/ai-scientist-output <job-id>                               # fetch artifacts
/ai-scientist-query <terms>                                 # search persistent knowledge store
/ai-scientist-meta                                          # meta-analysis view
/ai-scientist-resume <job-id>                               # resume failed job
```

Natural-language invocations also work — the skill auto-routes to the right agent subset:

```
review my paper at C:/papers/draft.tex                      # → Reviewer only
build plot for losses.npy                                   # → Plotter only
find papers on attention mechanisms                         # → LiteratureSearcher only
look at advanced NN algorithms and write code, then analyze # → Lit + CodeGen + Run + Plotter
```

## The 12 agents

| Agent | Model | Thinking | Role |
|---|---|---|---|
| ideator | opus | 48k | Structured idea + novelty check |
| codebase-scanner | sonnet | 8k | Repo audit |
| literature-searcher | sonnet | 8k | 6-source parallel search + dedup |
| hypothesizer | opus | 64k | Hypothesis + math models |
| code-generator | opus | 48k | Experiment script |
| experiment-runner | sonnet | 8k | Run + auto-fix |
| plotter | sonnet | 8k | Publication figures |
| manuscript-writer | opus | 48k | LaTeX (6 nested section subagents) |
| citator | sonnet | 8k | Citation enrichment |
| reviewer | opus | 64k | NeurIPS-format review + visual validation |
| meta-analyst | sonnet | 8k | Cross-job learning |
| fixer | sonnet | 16k | Error diagnosis + user-in-the-loop recovery |

Per-pipeline thinking-budget total: **272,000 tokens** across the 5 Opus agents + 48,000 across the Sonnet agents.

## Tweaking

User overrides go in `~/.claude/settings.json`:

```json
{
  "plugins": {
    "ai-scientist": {
      "agents": {
        "reviewer": { "model": "sonnet", "thinking_budget": 32000 }
      },
      "interactivity": "full",
      "literature": { "max_papers": 30 }
    }
  }
}
```

See `settings/settings.schema.json` for the full schema.

## Architecture

- **12 subagents** (`agents/`): each pinned to opus or sonnet with its own thinking budget
- **Orchestrator skill** (`skills/ai-scientist/SKILL.md`): owns file I/O + Phase −1 intent routing + dispatch
- **MCP server** (`mcp/server.py`): job registry, knowledge store (SQLite + ChromaDB), meta-analysis
- **Templates**: 5 LaTeX, 3 Word; visual validation pass on rendered PNGs
- **Runtime data**: `~/.ai-scientist/` (knowledge.db, jobs.json, trajectories.jsonl) — preserved across plugin reinstalls

## Spec & plan

- Design: `docs/specs/2026-04-25-ai-scientist-plugin-design.md`
- Implementation plan: `docs/plans/2026-04-25-ai-scientist-plugin-implementation.md`

## License

MIT — see LICENSE.
