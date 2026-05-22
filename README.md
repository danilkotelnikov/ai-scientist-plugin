# Vedix

An end-to-end agentic research workbench that turns a topic into a venue-ready manuscript. Runs natively inside Claude Code, Codex CLI, Gemini CLI, and Antigravity — same skill, same 17 subagents, same MCP servers, same artifact set on each host.

Vedix searches the literature, generates ideas, writes a hypothesis, codes and runs the experiment, drafts the manuscript, peer-reviews itself, validates every figure visually, and emits a compiled PDF plus a Word twin. Every numerical claim, citation, and figure caption is traced back to a source via the Source-Grounded Claim Architecture — the model cannot insert assertions that it didn't ground in a primary source.

## What it does

- **Literature → manuscript in one command.** Nine MCP-backed sources (OpenAlex, Semantic Scholar, arXiv, bioRxiv, PubMed, Anna's Archive, fetcher, plus the bundled knowledge store and per-project MemPalace memory) feed a pipeline of 17 specialized subagents.
- **Source-Grounded Claim Architecture (SGCA).** Every sentence in the manuscript is bound to an allowed-set of evidence drawn from the literature, the experiment ledger, and the codebase. The numerical-claim audit and the citation-graph audit re-verify before stage-gate exit.
- **Cross-host parity.** The same skill prompt and the same agent definitions run on Claude Code's `Task` tool, Codex's `spawn_agent`, and Gemini CLI's inline reasoning. Each agent declares per-host model pinning in its frontmatter.
- **23 publisher templates and seven first-class languages.** Render the same manuscript into Nature, Elsevier, IEEE, ACM, Frontiers, Wiley, Sage, MDPI, Springer-Nature, RSC, ACS, IOP, AIP, APS, Cell, PLOS, BMJ, Lancet, JAMA, Russian-region journals, and four more — in English, Russian, Spanish, German, French, Chinese, or Japanese.

## Install

One command on Linux, macOS, or Windows. The bootstrap detects which CLI hosts you have (Claude Code, Codex CLI, Gemini CLI), asks which to register into, installs Python deps, merges Codex config idempotently, runs the MCP self-test, and prints the slash commands you paste into Claude Code.

**Linux / macOS:**

```bash
curl -fsSL https://raw.githubusercontent.com/danilkotelnikov/vedix/master/scripts/bootstrap.sh | bash
```

**Windows (PowerShell):**

```powershell
iwr -useb https://raw.githubusercontent.com/danilkotelnikov/vedix/master/scripts/bootstrap.ps1 | iex
```

For Claude Code specifically, after the bootstrap finishes:

```
/plugin marketplace add danilkotelnikov/vedix
/plugin install vedix@vedix
```

Re-running is safe. The bootstrap is idempotent.

## Set one env var

OpenAlex made API access mandatory on 2026-02-13. Vedix uses your email as the polite-pool identifier:

```bash
export OPENALEX_EMAIL="you@example.com"
```

Everything else (Semantic Scholar key, Anna's Archive key, provider API keys) is optional and individually unlocks more functionality.

## Quickstart

From inside any supported host:

```
/vedix solvent polarity effects on Diels-Alder kinetics
```

Or in plain English — the skill auto-routes to the right subset of agents:

```
review my paper at C:/papers/draft.tex
build a plot from losses.npy
find papers on attention mechanisms
compare RWKV vs Mamba experimentally
```

Outputs land in `~/.vedix/jobs/<job_id>/`:

```
manuscript.pdf
manuscript.docx
manuscript.tex
references.bib
results.csv
experiment.py
figures/
sgca/sentence_ledger.jsonl
rigor/{citation_graph,counterfactual,adversarial_review,provenance}.json
logs/orchestrator.log
```

## How it works

The Python orchestrator at `plugins/vedix/mcp/lib/orchestrator/pipeline.py` owns retries, token accounting, semantic convergence, ensemble reviewers, stage-gate verification, and the SGCA ledger. The MCP server emits dispatch instructions; the host CLI invokes the matching subagent via its native mechanism and returns the output. The pipeline owns the state machine — agents are stateless workers.

| # | Subagent | Role |
|---|---|---|
| 1 | `ideator` | Generate research ideas, novelty-check against OpenAlex / Semantic Scholar |
| 2 | `codebase-scanner` | Map a target repo into entry points, modules, extension points |
| 3 | `literature-searcher` | Six-source parallel literature pull (one worker per source) |
| 4 | `hypothesizer` | Testable hypothesis with mathematical model + statistical framework |
| 5 | `code-generator` | Experiment script + `requirements.txt` per the domain template |
| 6 | `experiment-runner` | Install deps, run, parse stderr, patch up to 3 rounds |
| 7 | `tree-search-runner` | Best-First Tree Search variant explorer (gated on `--bfts`) |
| 8 | `plotter` | Three-cycle iterative figure refinement + Okabe-Ito palette |
| 9 | `paper-extractor` | Pull structured facts out of cited papers into the allowed-set |
| 10 | `manuscript-writer` | Six parallel section-writers (Abstract, Intro, Methods, Results, Discussion, Conclusion) |
| 11 | `citator` | Bidirectional citation enrichment, up to five rounds |
| 12 | `reviewer` | NeurIPS-style multi-pass adversarial review |
| 13 | `vlm-reviewer` | Vision-language figure review — duplicates, caption-content alignment |
| 14 | `meta-analyst` | Cross-job success-rate and failure-pattern aggregation |
| 15 | `fixer` | Diagnose pipeline failures and surface 2-4 fix options |
| 16 | `slide-presenter` | Beamer PDF + python-pptx editable deck + speaker notes |
| 17 | `codex-cross-validator` | Claude Code-exclusive — cross-checks every ideation, hypothesis, codegen, manuscript, review output against Codex via the [openai/codex-plugin-cc](https://github.com/openai/codex-plugin-cc) bridge |

## Source-Grounded Claim Architecture

Each manuscript sentence carries an entry in `sgca/sentence_ledger.jsonl`:

- The sentence text.
- The allowed set of supporting evidence (paper DOIs, experiment-result IDs, codebase line references).
- The verifier verdict (`supported` / `partial` / `unsupported`).
- The author agent and the timestamp.

Any sentence that fails verification triggers a re-write before the manuscript exits its stage gate. The same ledger drives the post-experiment numerical-claim audit (`numerical_audit.json`) and the citation-graph audit (`citation_graph.json`).

## Bundled MCP servers

The install registers nine MCP servers in your host config. Eight are external; one is bundled with Vedix.

| MCP | Source | Role |
|---|---|---|
| `vedix` | bundled | Knowledge store (SQLite FTS5 + ChromaDB), codebase analyzer, meta-analysis |
| `mempalace` | [MemPalace/mempalace](https://github.com/MemPalace/mempalace) | Per-project memory; auto-saves before context compaction |
| `openalex` | [drAbreu/alex-mcp](https://github.com/drAbreu/alex-mcp) | 240M+ scholarly works |
| `semanticscholar` | [JackKuo666/semanticscholar-MCP-Server](https://github.com/JackKuo666/semanticscholar-MCP-Server) | Semantic Scholar full API |
| `arxiv` | `arxiv-mcp-server` | Preprints (CS, physics, math, bio) |
| `biorxiv` | [JackKuo666/bioRxiv-MCP-Server](https://github.com/JackKuo666/bioRxiv-MCP-Server) | Life-sciences preprints |
| `pubmed` | `pubmed-mcp` | Biomedical literature |
| `annas-mcp` | `annas-mcp` | Anna's Archive full-text |
| `fetcher` | `fetcher-mcp` | HTTP fallback for Consensus and Crossref |

## Memory: per-project, no cross-project leakage

Two layers:

- **Cross-job global knowledge** — `~/.vedix/knowledge.db` (SQLite + ChromaDB). Papers, hypotheses, benchmark outcomes, claims, knowledge-graph triples, trajectories.
- **Per-project palace** — `<output_dir>/.palace/`. Wings → rooms → drawers (conversation context, agent diaries, intermediate states). Lives inside the job directory; deleting the project removes the palace.

Every agent calls `mcp__mempalace__wake_up(root="<output_dir>/.palace")` on entry and `mcp__mempalace__mine(root="<output_dir>/.palace")` on exit. Agents never read or write any other palace path.

## Native dispatch, BYOK as optional fallback

By default Vedix dispatches through the host CLI's native subagent mechanism (Task tool, `spawn_agent`, inline reasoning). The host's authentication carries the LLM cost — no extra API key needed.

If you want to route specific phases through a different provider, opt into the Bring-Your-Own-Key chain:

```bash
python -m vedix provider add anthropic --api-key "<key>"
python -m vedix provider add openai    --api-key "<key>"
python -m vedix provider set-chain anthropic openai
```

Fourteen providers supported: Anthropic, OpenAI, Google, DashScope (Qwen), GigaChat, Mistral, Cohere, plus seven more. Each adapter is lazily imported so installing only the SDKs you actually configure is fine.

## Configuration

User overrides go in `~/.claude/settings.json` (Claude Code), `~/.codex/config.toml` (Codex), or `~/.gemini/settings.json` (Gemini):

```json
{
  "plugins": {
    "vedix": {
      "agents": {
        "reviewer": { "model": "sonnet", "thinking_budget": 32000 }
      },
      "literature": { "max_papers": 30 },
      "experiment": { "use_bfts": true, "bfts_time_budget_minutes": 60 },
      "memory": { "scope": "project", "isolation": "strict" }
    }
  }
}
```

Full schema at [`plugins/vedix/settings/settings.schema.json`](plugins/vedix/settings/settings.schema.json).

## Tests

```bash
cd plugins/vedix && python -m pytest tests/
python plugins/vedix/mcp/server.py --selftest
```

The pytest suite covers per-host agent frontmatter, routing fixtures, the MCP self-test, the v2→v3 migration helper, and the orchestrator unit suite.

## Manual install paths

For each host, the bootstrap is the supported path. If it can't run in your environment, walk through the manual guides:

- Claude Code — [docs/INSTALL_CLAUDE_CODE.md](docs/INSTALL_CLAUDE_CODE.md)
- Codex CLI — [.codex/INSTALL.md](.codex/INSTALL.md)
- Gemini CLI — [.gemini/INSTALL.md](.gemini/INSTALL.md)
- LLM-driven — [docs/AGENT_INSTALL_PROMPTS.md](docs/AGENT_INSTALL_PROMPTS.md) (copy-paste prompts the agent follows)

## Credits

- [Sakana AI's AI-Scientist-v2](https://github.com/SakanaAI/AI-Scientist-v2) (MIT) — the canonical Python pipeline (BFTS, `perform_writeup`, `perform_vlm_review`, `perform_llm_review`, `perform_plotting`) is bundled under `plugins/vedix/mcp/lib/sakana/`.
- [MemPalace](https://github.com/MemPalace/mempalace) (MIT) — per-project memory DB.
- [drAbreu/alex-mcp](https://github.com/drAbreu/alex-mcp), [JackKuo666/semanticscholar-MCP-Server](https://github.com/JackKuo666/semanticscholar-MCP-Server), [JackKuo666/bioRxiv-MCP-Server](https://github.com/JackKuo666/bioRxiv-MCP-Server) — MCP wrappers for OpenAlex, Semantic Scholar, and bioRxiv.

## License

MIT — see [LICENSE](LICENSE).
