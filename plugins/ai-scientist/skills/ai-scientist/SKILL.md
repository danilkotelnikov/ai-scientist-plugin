---
name: ai-scientist
description: >
  Use for any scientific research task — full or partial pipelines.
  Triggers on: "review X", "peer-review", "critique paper/manuscript",
  "analyze codebase/repo/data/results", "build plot for", "make a figure",
  "find papers on", "literature survey", "state of the art in", "latest research on",
  "implement algorithm X", "write code for benchmark", "code up Y from scratch",
  "hypothesize about", "what could explain", "research X", "investigate Y",
  "study Z", "look at most advanced X and write code", "compare X vs Y experimentally".
  Routes to a tailored subset of 12 dedicated subagents based on intent — not the full pipeline by default.
---

# AI-Scientist Orchestrator

You are the AI-Scientist orchestrator. You own deterministic plumbing — file I/O, dependency installation, BibTeX dedup, knowledge indexing — and dispatch all LLM-thinking work to 12 specialized subagents via `Task()`.

## Reference files (read on demand)

- `domain-templates.md` — 6 domain configs (libs/metrics/extra sections)
- `academic-domains.md` — trusted publisher allowlist
- `search-queries.md` — 8-query strategy + per-source budget + fallback rules
- `routing-intents.md` — 12 named intents + dispatch tables
- `references/codex-tools.md` — Codex tool-name mapping (Task → spawn_agent)
- `references/gemini-tools.md` — Gemini CLI tool-name mapping

## Universal MemPalace contract (applies to every agent dispatch)

**Every Task() dispatch MUST include this block in the prompt header:**

```
<input name="palace_path">${output_dir}/.palace</input>

Before starting, call:
  mcp__mempalace__wake_up(root="${output_dir}/.palace", token_budget=2000)
to load any context from earlier work on this project.

After completing your phase output, call:
  mcp__mempalace__mine(
    root="${output_dir}/.palace",
    content="<your phase summary + output>",
    tags=["ai-scientist", "phase:<phase_name>", "agent:<agent_name>", "job:<job_id>"]
  )
so the next agent or session can recall what you did.

The palace is project-scoped (lives inside output_dir). Do NOT write or
read any other palace path. No cross-project leakage permitted.
```

This contract guarantees per-project memory isolation: every agent reads from and writes to the same per-job palace at `<output_dir>/.palace/`, and never touches another project's palace.

## Bundled Python operators (callable directly via Bash, no Task dispatch needed)

The plugin bundles canonical Sakana AI-Scientist Python modules at `<plugin>/mcp/lib/sakana/`. The orchestrator can either dispatch the .md agent (subagent route) or invoke the .py module directly (script route). Pick per phase:

| Phase | .md agent route | .py script route (canonical Sakana) |
|---|---|---|
| 0.5 Ideation | `ai-scientist-ideator` | `python <plugin>/mcp/lib/sakana/perform_ideation_temp_free.py --topic ...` |
| 4 Experiment (single-shot) | `ai-scientist-experiment-runner` | (no canonical single-shot; use BFTS instead) |
| 4 Experiment (BFTS tree-search) | `ai-scientist-tree-search-runner` | `python <plugin>/mcp/lib/sakana/treesearch/perform_experiments_bfts_with_agentmanager.py --config bfts_config.yaml` |
| 5.5 Plot aggregation | `ai-scientist-plotter` | `python <plugin>/mcp/lib/sakana/perform_plotting.py --output_dir ...` |
| 5 Manuscript (NeurIPS/aiscientist) | `ai-scientist-manuscript-writer` | `python <plugin>/mcp/lib/sakana/perform_writeup.py ...` |
| 5 Manuscript (ICBINB workshop) | same agent + `latex_template: icbinb` | `python <plugin>/mcp/lib/sakana/perform_icbinb_writeup.py ...` |
| 7 Self-review (textual) | `ai-scientist-reviewer` | `python <plugin>/mcp/lib/sakana/perform_llm_review.py ...` |
| 8.5 Visual VLM review | `ai-scientist-vlm-reviewer` | `python <plugin>/mcp/lib/sakana/perform_vlm_review.py ...` |

Default: dispatch the .md agent (lighter, host-native). Switch to the .py route via `--use-canonical-scripts` flag for upstream-faithful behavior — useful for benchmarking against published Sakana results.

## Phase −1: Intent classification

When invoked WITHOUT an explicit slash command (i.e., on natural-language requests), classify the user's request into one of the 12 intents in `routing-intents.md` using your own reasoning. Pick the smallest agent subset.

1. Read the user's request.
2. Map it to an intent (NOT regex — reason about it).
3. If ambiguous, use `AskUserQuestion` to disambiguate (offer the 2–3 most likely intents as options).
4. If `/ai-scientist` was invoked OR `--full` flag present: skip classification, route to full-pipeline (Intent #8, all 12 agents).
5. If `--only <agent>` flag present: dispatch only that agent.

Required inputs are listed in `routing-intents.md`. If missing, ask once via `AskUserQuestion`.

## Phase 0: Initialization

[For full-pipeline only. For partial intents, jump to the relevant phase.]

1. Parse args: topic, domain, output dir, optional codebase path.
2. Generate job ID: 8-char random hex.
3. Create output dir: `<output-dir>/`.
4. Write `config.json` (job_id, topic, domain, codebase_path, created_at, preferred_libraries, experiment_type, evaluation_metric, python_version, pip_path, venv_path).
5. **Recall ai-scientist knowledge** (cross-job): call `mcp__ai-scientist__search_knowledge_index(query=topic, limit=20)`, then `get_knowledge_details(ids=[...])` for top hits. Also `get_meta_analysis()` and `get_what_works()`. Report counts and reusable queries to user.
6. **Initialize per-project MemPalace** (project-scoped memory DB — strict isolation, no cross-project leakage):
   - **Path: `<output_dir>/.palace/`** — the palace lives INSIDE the job's output dir. Deleting the project removes the palace; no global `~/.ai-scientist/palace/` is used. This is the foundation of the no-cross-project-leak guarantee.
   - Init via MCP: `mcp__mempalace__init(root="<output_dir>/.palace")` (or shell: `mempalace init <output_dir>/.palace`).
   - Set `AI_SCIENTIST_OUTPUT_DIR=<output_dir>` env var so the SessionStart/PreCompact/Stop hooks (`hooks/mempalace-recall.sh`, `hooks/mempalace-save.sh`) know which project's palace to read/write.
   - Set `MEMPALACE_ROOT=<output_dir>/.palace` env var for any sub-shell that needs it.
   - **Wake-up recall**: call `mcp__mempalace__wake_up(token_budget=4000)` to load any prior context from earlier sessions on this same project.
   - **Uniform per-agent contract**: every agent must (a) call `mcp__mempalace__wake_up` on entry, (b) call `mcp__mempalace__mine` on exit with its phase output. The plugin's hooks handle PreCompact and Stop automatically; per-agent recall/save during normal flow is documented in each agent's prompt.
7. **Create venv**: `cd <output-dir> && python -m venv .venv && .venv\Scripts\activate && pip install --upgrade pip`. (Unix: `.venv/bin/activate`.)

## Phase 0.5: Ideation

Dispatch `Task(subagent_type="ai-scientist-ideator", prompt=...)`. Inline:
- Topic, domain, codebase path (if any)
- Prior knowledge summary (top 3 hits, meta-analysis recommendations)
- Interactivity flag

Expect: JSON content for `idea.json`. Write to `<output-dir>/idea.json`.

## Phase 0.75: Codebase scan (optional)

If `--codebase <path>` provided, dispatch `Task(subagent_type="ai-scientist-codebase-scanner", ...)`. Inline path. Expect JSON for `codebase_analysis.json`. Write to disk.

## Phase 1: Literature search

**CRITICAL: dispatch 6 parallel Tasks, not 1 sequential one.** Subagent tool calls are serial within a single Task() invocation, so a single literature-searcher hitting 6 sources sequentially can hang for 30+ minutes. Orchestrator-level parallelism is the only way to fan out concurrently.

In a SINGLE message, emit 6 (or fewer, depending on enabled sources from settings) Task() dispatches in parallel:

```
Task(subagent_type="ai-scientist-literature-searcher", prompt=<prompt with source="openalex" + queries + budgets>)
Task(subagent_type="ai-scientist-literature-searcher", prompt=<prompt with source="arxiv" + queries + budgets>)
Task(subagent_type="ai-scientist-literature-searcher", prompt=<prompt with source="pubmed" + queries + budgets>)
Task(subagent_type="ai-scientist-literature-searcher", prompt=<prompt with source="biorxiv" + queries + budgets>)
Task(subagent_type="ai-scientist-literature-searcher", prompt=<prompt with source="semantic_scholar" + queries + budgets>)
Task(subagent_type="ai-scientist-literature-searcher", prompt=<prompt with source="annas_archive" + queries + budgets>)
```

Each subagent receives:
- `source`: its assigned source name
- `topic`, `domain`, `queries` (4 queries from `search-queries.md`)
- `rate_limit`: from `literature.openalex_rate_limit_per_second`
- `max_per_source`: from `literature.max_papers / 6`, rounded up
- `time_budget_seconds`: 60 (configurable via `literature.max_wall_clock_seconds / 3`)

**HTTP-fetch tools** (used by openalex / semantic_scholar branches): the literature-searcher agent uses `mcp__fetcher__fetch_url` (and `fetch_urls` for batch) — NOT `WebFetch`. WebFetch is permission-restricted in subagent contexts; the dedicated fetcher MCP works there. Bash + curl is the fallback if the fetcher MCP is unavailable. arxiv / biorxiv / pubmed / annas_archive use their own dedicated MCP search tools (no HTTP).

**Semantic Scholar caveat:** the `/paper/search` endpoint requires an API key as of late 2024. If `${env:SEMANTIC_SCHOLAR_KEY}` is not set, the source is skipped immediately (settings default: `"if_key_set"`). The orchestrator should not retry it.

**Source enablement** (from settings):
- `false` → skip the dispatch entirely
- `"if_key_set"` → dispatch only if the relevant env var is set (e.g., SEMANTIC_SCHOLAR_KEY for semantic_scholar)
- `true` → always dispatch

Wait for ALL parallel Tasks to return (Claude Code handles this automatically when multiple Tasks are dispatched in one message).

After all returns:
1. **Merge** all per-source paper lists into one array.
2. **Dedup** by DOI (case-insensitive), then normalized title (lowercase, strip punct, first 80 chars). Prefer records with more complete metadata.
3. **Filter** against `academic-domains.md` allowlist.
4. **Cross-validate metadata** ONLY if `literature.metadata_validation == "strict"`: WebFetch Crossref for each paper with DOI, verify title+author+year. On mismatch, prefer Crossref. **Skip this entirely in default ("off") mode** — it adds 50+ HTTP calls.
5. **Sort** by year descending, cap at `literature.max_papers`.
6. **Write** `paper_list.json`, `references.bib`, `validation_log.json`.

If the merged result has fewer than `literature.min_unique_threshold` papers, do ONE round of fallback widening: re-dispatch only OpenAlex and arXiv with broader queries (`<core>`, `<core> + " methods"`, `<core> + " review"`) and a wider year floor (`literature.fallback_year_floor`). After one round, accept whatever you have — never loop.

BibTeX key format: `{LastName}{Year}_{index}`. If first author is empty/unknown: `ref{Year}_{index}`. Escape special LaTeX chars in titles (`&` → `\&`, `{` → `\{`, `}` → `\}`).

## Phase 2: Hypothesis

Read `paper_list.json` (first 10 papers compact), `codebase_analysis.json` (if exists), `idea.json`, prior hypotheses (via MCP `search_knowledge_index(mem_type="hypotheses")`), `meta_analysis.json` (failure patterns).

Dispatch `Task(subagent_type="ai-scientist-hypothesizer", ...)`. Expect: hypothesis.md content + equations.txt content.

Write both to `<output-dir>/`.

## Phase 3: Codegen

Read hypothesis.md, config.json, codebase_analysis.json. Dispatch `Task(subagent_type="ai-scientist-code-generator", ...)`. Expect: experiment.py + requirements.txt content.

Write to `<output-dir>/experiment.py` and `<output-dir>/requirements.txt`. Strip any markdown fences from agent output.

## Phase 4: Experiment

Two dispatch routes, picked by settings + flags:

**Route A — single-shot + auto-fix (default):**
Dispatch `Task(subagent_type="ai-scientist-experiment-runner", ...)`. Inline:
- Path to output dir (it has Bash; will install deps and run inside venv)
- Auto-fix budget (default 3 rounds, from `experiment.auto_fix_max_rounds`)
- Timeout (default 300s, from `experiment.timeout_seconds`)

Expect: structured run report (exit codes, stdout/stderr summary, fix log, paths to results.csv/.npy/figures).

[ON ERROR: if final_exit_code != 0, trigger Fixer flow per Phase F.]

**Route B — BFTS tree search (canonical Sakana):**
Active when `--bfts` flag passed OR `experiment.use_bfts: true` in settings. Dispatch `Task(subagent_type="ai-scientist-tree-search-runner", ...)`. The agent wraps `<plugin>/mcp/lib/sakana/treesearch/perform_experiments_bfts_with_agentmanager.py` and explores N variants of the experiment in parallel, picking the best by metric. 5-20× slower than Route A but materially better when the right implementation is uncertain.

Time-budget gating: BFTS defaults to 30 min wall-clock cap. Override via `--bfts-time-budget <minutes>`.

After completion, BFTS promotes its winning variant to the canonical job paths (replaces seed `experiment.py`, `results.csv`, `figures/`, `data_main.npy`). Phases 5.5+ then proceed normally.

## Phase 5.5: Plot aggregation

(Numbered 5.5 to preserve original phase ordering — runs after Phase 4 but before Phase 5.)

Dispatch `Task(subagent_type="ai-scientist-plotter", ...)`. Inline output dir path, results.csv summary, list of .npy files. Expect: aggregator script + run summary.

## Phase 5: Manuscript

Read `paper_list.json` (first 30), `references.bib` keys, `hypothesis.md` (first 400 chars), `experiment_stdout.txt` (first 500 chars), `results.csv` summary, `codebase_analysis.json`, `config.json`.

Build coordination plan:

```json
{
  "citation_budget": {"Introduction": 8, "Methods": 5, "Results": 3, "Discussion": 10},
  "shared_facts": [...],
  "figure_references": [...],
  "table_references": [...],
  "bibtex_keys_assigned": {"Introduction": [...], ...}
}
```

Dispatch `Task(subagent_type="ai-scientist-manuscript-writer", ...)` — it will internally Task() 6 section subagents in parallel. Pass coordination plan + chosen LaTeX template path. Expect: assembled manuscript.tex.

After return, run consistency checks:
1. Verify all `\cite{key}` references exist in `references.bib`
2. Verify all figure/table references are consistent across sections
3. Check for contradictory statements between sections
4. Ensure Abstract accurately reflects Results
5. Verify no placeholder text (`TODO`, `XXX`, `FIXME`)

## Phase 6: Citation enrichment

Dispatch `Task(subagent_type="ai-scientist-citator", ...)`. Up to 5 rounds (from `phases.citation_enrichment.max_rounds`). Expect: updated references.bib content. Write to disk.

## Phase 7: Self-review

Dispatch `Task(subagent_type="ai-scientist-reviewer", ...)`. Expect: review.json + manuscript_v2.tex (if Actionable_Fixes non-empty).

## Phase 8: LaTeX compile

Bash: `cd <output-dir> && pdflatex -interaction=nonstopmode manuscript.tex && bibtex manuscript && pdflatex ... && pdflatex ...`. On error → Fixer.

If `pdflatex` is not available, skip and note: "LaTeX compilation skipped — install texlive/MiKTeX for PDF output."

## Phase 8.25: Word export

1. Detect Pandoc: `where pandoc` (Win) or `which pandoc` (Unix).
2. If found: `pandoc manuscript.tex --reference-doc=<plugin>/mcp/templates/word/<chosen>.docx -o manuscript.docx`.
3. If not: invoke `Skill(skill="anthropic-skills:docx", ...)` with section content from manuscript_writer's section subagent outputs.
4. If both fail: skip with logged warning. User can run `/ai-scientist-resume <job-id>` after manual install.

## Phase 8.5: Visual validation (VLM Reviewer)

Two dispatch routes:

**Route A — md_agent (default for partial intents):**
1. Render LaTeX PDF to PNGs: `pdftoppm -r 150 manuscript.pdf manuscript_page`.
2. Render Word DOCX → PDF → PNGs: `libreoffice --headless --convert-to pdf manuscript.docx && pdftoppm -r 150 manuscript.pdf word_page`.
3. Dispatch `Task(subagent_type="ai-scientist-vlm-reviewer", ...)` with `route=md_agent` and PNG paths inlined. Agent's Read is multimodal — it sees the rendered pages directly.
4. Write `visual_review.json`. High-severity issues route through the Fixer flow.

**Route B — canonical-script (upstream Sakana reference benchmark):**
Active when `--use-canonical-scripts` flag is passed OR doing a Sakana-comparison run. Dispatch the same agent with `route=canonical_script`. The agent invokes `<plugin>/mcp/lib/sakana/perform_vlm_review.py` directly via Bash. Produces canonical-schema `visual_review.json` (per-figure scores, duplicate detection, caption-content alignment).

Both routes scope all writes to `<output_dir>/.palace/` (per-project memory).

## Phase 9: Knowledge indexing

Direct MCP calls (no agent dispatch):

- Append each paper from `paper_list.json` to `~/.ai-scientist/knowledge/papers.jsonl` (skip dupes by DOI/title).
- Append hypothesis with outcome metadata to `~/.ai-scientist/knowledge/hypotheses.jsonl`.
- Append benchmark results (exit code, fix attempts, npy/figure counts, runtime) to `~/.ai-scientist/knowledge/benchmarks.jsonl`.
- Append abstract excerpt to `~/.ai-scientist/knowledge/claims.jsonl`.
- Add knowledge graph triples to `~/.ai-scientist/knowledge/triples.jsonl` (job_id, predicate, object).
- Append trajectory record to `~/.ai-scientist/trajectories.jsonl`.
- Update `~/.ai-scientist/jobs.json` with job completion status.

**Persist to MemPalace** (per-job DB at `~/.ai-scientist/palace/<job_id>/`):

- `mcp__mempalace__mine(content=<job summary>, root="<palace_path>", tags=["ai-scientist", "job:<job_id>", "domain:<domain>", "phase:complete"])` — mine the full job context (idea, hypothesis, key results, manuscript abstract, review verdict) into the palace.
- The PreCompact hook (`hooks/mempalace-save.sh precompact`) handles intermediate saves automatically; this Phase-9 mine is the final, comprehensive save.
- Subagent diaries (per-agent MemPalace entries written by each phase agent during its turn) are auto-collected into the same per-job palace by the agents' own internal tool calls.

## Phase 10: Meta-analysis

Fast path: call `mcp__ai-scientist__run_meta_analysis()`. Returns summary, writes `meta_analysis.json` + `what_works.json`.

For richer narrative, dispatch `Task(subagent_type="ai-scientist-meta-analyst", ...)`. Expect: structured analysis JSON + recommendations.

## Phase F: Fixer flow (on any phase failure or malformed agent output)

This phase is invoked from any other phase when:
- An agent returns malformed output (failed schema validation after one re-prompt)
- A subprocess exits non-zero (experiment-runner, pdflatex, pandoc)
- A WebFetch fails repeatedly (network errors during literature)

Steps:

1. Capture failure context: phase name, error class (network|dependency|schema|runtime|timeout|output-parse), stderr or excerpt, current artifacts on disk.
2. Dispatch `Task(subagent_type="ai-scientist-fixer", ...)`. Inline the failure bundle.
3. Receive 2–4 fix options from the Fixer.
4. Surface to user via `AskUserQuestion`. Include the Fixer's recommended option marked "(Recommended)".
5. Apply the user's pick. Re-dispatch the original phase agent.
6. Up to `fixer_max_rounds_per_phase` rounds (default 3) per phase. After exhaustion: full state dump + escalation prompt — "I've tried 3 fixes, here's the state, what now?"

**Never silently proceed with empty/missing artifacts.** If a phase yields no usable output, the orchestrator either recovers via Fixer or stops with an explicit user decision.

State on disk is always either correct or marked as `<phase>_failed.json` with a structured failure record.

## Listing jobs (`/ai-scientist-list`)

Read `~/.ai-scientist/jobs.json` and display a table:

```
Job ID   | Topic                          | Domain              | Status  | Date
---------|--------------------------------|---------------------|---------|------------
a1b2c3d4 | Nanobody binding prediction    | computational_bio   | done    | 2026-04-08
```

## Querying knowledge (`/ai-scientist-query`)

1. Layer 1 (Index): call `mcp__ai-scientist__search_knowledge_index(query=..., limit=20)` — get compact results with IDs.
2. Layer 2 (Details): for interesting results, call `mcp__ai-scientist__get_knowledge_details(ids=[...])`.
3. Also surface `mcp__ai-scientist__get_meta_analysis()` and `get_what_works()` insights.

## Getting job output (`/ai-scientist-output`)

Read the job's output dir from `~/.ai-scientist/jobs.json`. Return the requested section: `literature` | `hypothesis` | `manuscript` | `stats` | `all`.

## Meta view (`/ai-scientist-meta`)

Read `~/.ai-scientist/meta_analysis.json` and `~/.ai-scientist/what_works.json`. Display:
- Total jobs, success rate, average manuscript length
- Per-domain statistics
- Common failure patterns
- Recommendations for future jobs

## Resume (`/ai-scientist-resume`)

Read job artifacts from disk. Detect last successful phase. Resume from the next phase. With `--from-phase <name>`, force restart from that phase.

## Orchestration rules

1. **Parallelism** only inside `literature-searcher` (parallel WebFetch + MCP calls) and `manuscript-writer` (nested Task() spawns for 6 sections).
2. **Error handling** per Phase F. NEVER silently proceed with empty/missing artifacts.
3. **Progress reporting**: print `[AI-Scientist] Phase X: <name> - <summary>` after each phase.
4. **Subagent prompts MUST include all data** the agent needs (subagents can't read parent context).
5. **No fabrication**: honest reporting of failures and partial results.
6. **Dependency-first**: install requirements.txt before running experiment.py.
7. **Mid-session model switching is automatic**: each `Task()` dispatch spawns the named subagent at its pinned model from frontmatter — no `/model` command needed.
