# AI-Scientist Plugin — Orchestrator Rewrite (Approach B′)

- **Date:** 2026-04-27
- **Author:** scienceboylovesyou@gmail.com
- **Status:** Approved for writing-plans
- **Replaces:** the prose-only orchestration in `skills/ai-scientist/SKILL.md`
- **Targets:** ~95 % feature parity with canonical Sakana AI-Scientist v2 + 4 capabilities Sakana lacks
- **Effort:** ~3 weeks
- **Predecessor spec:** `docs/specs/2026-04-25-ai-scientist-plugin-design.md`

---

## 0. Problem statement

The plugin shipped 1,337 LOC of cross-validation glue, 9 pre-configured MCPs, MemPalace per-project memory, vendored canonical Sakana, and three-host parity — but a smoke test on `04a21066` revealed **slow runtime, low quality output, and missing v2 techniques**:

- **Manuscript factual error**: Conclusion claims `\|d\|` "grows monotonically from 0.22 to 1.31" — Table 1 shows it dips from 0.62 → 0.48 between α=0.5 → α=1 before resuming growth.
- **3 uncited bibliography entries** (`Wang2022_7`, `Verrelst2021_9`, `Shen2013_14`) present in `references.bib` but never referenced in body.
- **Novelty check skipped** (`"refinement_applied": "Skipped per smoke-test instructions"`).
- **Single-opinion review** (one Opus pass scored 5/10, no calibration).

A four-agent investigation cross-validated against canonical Sakana v2 source, Anthropic agent docs, superpowers skills, and 13 best-in-class OSS agentic plugins. Root cause: **the plugin is 100% prose-orchestrated.** Every phase is a `.md` agent dispatched via `Task()` with no Python loop owning state, retries, token tracking, semantic convergence, structured outputs, ensemble aggregation, or error injection. v2 has decorator-based retry/tracking, multi-round reflection with error injection, multiple ideation candidates with archiving, ensemble reviewers with bias prompts, few-shot grounding, two-tier JSON extraction, and stage-based checkpointing — **none of which can be reproduced in `.md` prose alone**.

This spec rewrites the orchestration layer in Python while keeping the 15 `.md` agents as prompt templates and preserving cross-host parity (Claude Code / Codex / Gemini).

## 1. Goals (in priority order)

1. **Reproduce v2's quality-bearing techniques** — multi-round reflection, multiple candidates, ensemble reviewers, semantic convergence, error injection, few-shot grounding, structured JSON extraction, stage-based checkpointing, decorator-based retry & token tracking.
2. **Preserve cross-host parity** — same skill, same agents, same MCPs on Claude Code / Codex CLI / Gemini CLI. Per-host model pinning intact.
3. **Add capabilities v2 lacks** — Codex cross-validation (existing), MemPalace per-project memory (existing), bidirectional `\cite{}` ↔ `.bib` validation, slide generation, narrative-memory `findings.md` schema, plan persistence with superpowers integration.
4. **Hard guarantees** — never hangs, every Codex call has a timeout, every phase has a verification gate before commit, every irreversible decision has an `AskUserQuestion` gate (when interactivity allows).
5. **Auditable** — token usage tracked per phase per agent in USD; every phase advancement logged to MemPalace; every plan and spec auto-mined; resume from any phase boundary.

## 2. Non-goals (YAGNI)

- Replacing the 15 `.md` agents with pure-Python equivalents. They stay as prompt templates.
- Replacing MemPalace, the Codex bridge, or the 9 MCPs with anything new. They keep working.
- BFTS as the default for non-compute-heavy phases. Stays opt-in via `--bfts`.
- Integrating A-EVOLVE in v1 (deferred to v2 if persistent cross-job evolution becomes a need).
- Bundling Orchestra-Research/AI-Research-SKILLs as a marketplace dep. Selective vendoring only (4 specific assets).

## 3. Architecture

### 3.1 Inversion: Python orchestrator owns state, .md files become prompt templates

```
Before                                   After
──────                                   ─────
SKILL.md (orchestrator, ~600 lines)      SKILL.md (~150 lines, intent routing only)
   ↓ Task(subagent_type=...)                ↓ mcp__ai-scientist__run_pipeline(...)
.md agent (prompt + frontmatter)         orchestrator/pipeline.py
   ↓ returns string                         ↓ uses dispatch.py to call:
parsed in SKILL.md                       .md agent (prompt template)
   ↓ next Task() call                       ↓ Python ReflectionLoop owns:
                                           • retry + backoff
                                           • token tracking
                                           • semantic convergence
                                           • error injection
                                           • ensemble aggregation
                                           • structured JSON extraction
                                           • stage-gate verification
                                           • checkpoint persistence
```

The 15 `.md` agent files **stay** as prompt templates. The Python orchestrator reads them, strips frontmatter, fills `<input name="...">` placeholders with actual data, and dispatches via the host's native subagent surface — but inside Python loops with all the v2 machinery.

### 3.2 New modules under `mcp/lib/orchestrator/`

```
orchestrator/
├── __init__.py
├── decorators.py        # @retry_with_backoff, @track_tokens, @log_phase
├── schemas.py           # strict JSON schema definitions per phase output
├── extraction.py        # two-tier JSON/LaTeX/Python extractor with AST validation
├── convergence.py       # semantic-signal detection ("I am done", "FinalizeIdea")
├── reflection.py        # multi-round refinement loop with error injection
├── ensemble.py          # bias-prompted multi-reviewer + numpy aggregation
├── fewshot.py           # few-shot example injection from mcp/templates/fewshot/
├── pipeline.py          # phase orchestrator (replaces SKILL.md's loop logic)
├── tokens.py            # token tracker (sums prompt/completion/thinking, USD est)
├── checkpoints.py       # per-stage pickle of journal + config (resume-from-stage)
├── status.py            # DONE / DONE_WITH_CONCERNS / BLOCKED / NEEDS_CONTEXT enum
├── stage_gate.py        # structured eval specs between phases (per Sakana AgentManager)
├── references.py        # bidirectional \cite{} ↔ .bib + Crossref validation
├── findings.py          # findings.md scaffold (vendored from AI-Research-SKILLs)
├── superpowers_bridge.py # writing-plans/executing-plans/subagent-driven-dev wrappers
├── mempalace_helpers.py # PluginPalace + ProjectPalace ergonomic wrappers
└── dispatch/
    ├── __init__.py      # exports get_dispatcher() based on detected host
    ├── claude_code.py   # ClaudeCodeDispatcher (uses Task tool via MCP)
    ├── codex.py         # CodexDispatcher (uses spawn_agent)
    └── gemini.py        # GeminiDispatcher (inline reasoning fallback)
```

### 3.3 SKILL.md becomes thin

Trims from ~600 lines to ~150. Responsibilities:
- Phase −1 intent classification (still LLM reasoning over 12 named intents)
- Calling the Python pipeline via a single MCP tool: `mcp__ai-scientist__run_pipeline(topic, domain, output_dir, intent, interactivity, ...)`
- Surfacing `AskUserQuestion` gates raised by the pipeline
- Reporting progress via stdout

The pipeline does everything else.

### 3.4 Three host-dispatch backends

| Host | Backend | Mechanism |
|---|---|---|
| Claude Code | `ClaudeCodeDispatcher` | Surfaces an MCP tool `mcp__ai-scientist__dispatch_phase(agent_name, inputs)` that internally invokes `Task(subagent_type="ai-scientist-<agent_name>", prompt=...)` |
| Codex CLI | `CodexDispatcher` | Uses `spawn_agent(agent_type="worker", message=...)` per the Codex tool-mapping reference |
| Gemini CLI | `GeminiDispatcher` | Falls back to inline reasoning since Gemini lacks Task — pipeline executes the agent prompt in the current session |

Auto-detected via the existing `detect_host()` from `codex_bridge`. Backend is plugged into `pipeline.py` at construction; the rest of the loop logic is host-agnostic.

## 4. Components — module-by-module spec

### 4.1 `decorators.py`

```python
@retry_with_backoff(max_tries=5, max_time=300, on=(RateLimitError, APITimeoutError))
@track_tokens(phase="ideation", agent="ideator")
@log_phase
def call_agent(agent_name, prompt, model, **kw): ...
```

Lifted from `mcp/lib/sakana/llm.py:77-86`. Uses the `backoff` library (already a transitive dep via Sakana's vendored code).

### 4.2 `tokens.py`

```python
class TokenTracker:
    def add(self, phase, agent, prompt_tok, completion_tok, thinking_tok=0): ...
    def total_cost_usd(self) -> float: ...
    def report(self) -> dict: ...
    def warn_if_over_budget(self, budget_usd): ...
```

Singleton per pipeline run. Logged to `<output_dir>/.palace/` and surfaced in the final job summary. Pricing table in `settings.codex_bridge.pricing`. Closes the ~450k-tokens/job invisible cost.

### 4.3 `schemas.py`

```python
IDEATION_SCHEMA = {"type": "object", "required": ["Name", "Title", "Short_Hypothesis", ...]}
HYPOTHESIS_SCHEMA = {...}
REVIEW_SCHEMA = {...}
```

Two enforcement points: (1) `strict: true` on the agent's tool-use schema where supported, (2) `jsonschema.validate()` on parsed output before accepting. Schema-violation → re-prompt with the validator's error inlined, max 2 re-prompts, then escalate to Fixer.

### 4.4 `extraction.py`

```python
extract_json(text) -> dict       # ```json block → balanced-brace scan → control-char strip → json.loads
extract_latex(text) -> str       # ```latex block → unwrap fences
extract_python(text) -> str      # ```python block → ast.parse() validate before returning
```

Three-tier fallback per Sakana's `llm.py:452-477`. Python extraction adds AST validation — catches syntax errors at Phase 3 instead of Phase 4.

### 4.5 `convergence.py`

```python
class SemanticConvergence:
    signals = ["I am done", '"action": "FinalizeIdea"', "no further changes needed"]
    def is_converged(self, llm_response: str) -> bool: ...
```

Loops terminate on LLM signal, not fixed round count. Per `perform_writeup.py:693-707`. Settings cap at `max_rounds` as fallback.

### 4.6 `reflection.py`

```python
class ReflectionLoop:
    def run(self, agent_md, inputs, max_rounds=5, error_injection=True) -> dict:
        history = []
        for round_n in range(max_rounds):
            response = dispatch(agent_md, inputs, prior_attempts=history)
            try:
                parsed = extract_and_validate(response, schema)
            except SchemaError as e:
                history.append({"round": round_n, "response": response, "error": str(e)})
                continue
            if convergence.is_converged(response):
                return parsed
            critique = self.evaluator(parsed)  # PASS / NEEDS_IMPROVEMENT / FAIL
            if critique.verdict == "PASS":
                return parsed
            history.append({"round": round_n, "response": response, "critique": critique.reason})
        return parsed  # accept best after max rounds
```

Used by Phases 0.5, 2, 3, 5, 7. Closes Gaps #3, #4, #5 (multi-round refinement, error injection, multiple candidates implicit via reflection).

### 4.7 `ensemble.py`

```python
class BiasedReviewers:
    def review(self, manuscript, n=3) -> ReviewAggregate:
        reviews = [
            dispatch(reviewer_md, manuscript, system_bias="positive"),
            dispatch(reviewer_md, manuscript, system_bias="negative"),
            dispatch(reviewer_md, manuscript, system_bias="neutral"),
        ]
        # numpy aggregate scores, flag outliers >1.5 IQR
        return ReviewAggregate(median_score=..., consensus_high=..., disagreements=...)
```

Direct port of `perform_llm_review.py:17-24, 150-202`. The 3 dispatches run in parallel (orchestrator emits 3 `Task()` calls in one batch).

### 4.8 `fewshot.py`

```python
class FewShotInjector:
    def inject(self, agent_prompt: str, examples: list[Path]) -> str:
        # Reads templates/fewshot/{attention,carpe_diem,automated_relational}.{pdf,json,txt}
        # Prepends as `<example>...</example>` blocks
```

Activates for: ideator (paper exemplars), hypothesizer (well-formed hypothesis exemplars), reviewer (review exemplars). Files exist at `mcp/templates/fewshot/` but are currently never used.

### 4.9 `status.py`

```python
class AgentStatus(Enum):
    DONE = "done"
    DONE_WITH_CONCERNS = "done_with_concerns"
    BLOCKED = "blocked"
    NEEDS_CONTEXT = "needs_context"
```

Every agent return value includes `status: AgentStatus`. Decision tree per superpowers' `subagent-driven-development`:
- `BLOCKED` → re-dispatch with stronger model OR escalate via `AskUserQuestion`
- `DONE_WITH_CONCERNS` → log concerns, proceed
- `NEEDS_CONTEXT` → orchestrator extracts requested context from disk/MCP, re-dispatches

### 4.10 `pipeline.py`

```python
class Pipeline:
    def run_full_pipeline(self, topic, domain, output_dir):
        with TokenTracker() as tt, ProjectPalace(output_dir / ".palace") as palace:
            self.phase_0_init(...)
            candidates = self.phase_0_5_ideation(topic, domain, num_candidates=3)
            idea = self.user_picks_idea(candidates)              # AskUserQuestion gate #2
            papers = self.phase_1_literature(idea)
            self.user_confirms_coverage(papers)                  # gate #4
            hypothesis = self.phase_2_hypothesis(idea, papers)   # ReflectionLoop
            code = self.phase_3_codegen(hypothesis)              # AST-validated, ReflectionLoop on syntax error
            results = self.phase_4_experiment(code)              # auto-fix loop, optionally BFTS
            ...
            review = self.phase_7_review(manuscript)             # BiasedReviewers ensemble
            self.phase_9_index_knowledge(...)
            self.phase_10_meta_analysis(...)                     # updates findings.md
            slides = self.phase_11_slides(manuscript)            # NEW
            tt.report()                                          # token usage + cost summary
```

### 4.11 `stage_gate.py`

```python
class StageGate:
    def gate(self, phase: str, artifacts: dict) -> StageGateResult:
        # Calls a small structured-output LLM eval per Sakana's stage_progress_eval_spec
        # Returns: {ready_for_next_stage: bool, missing_criteria: [...]}
```

Run between every major phase boundary. Block phase advancement on `ready=false`. Closes the "writing manuscripts on incomplete experiments" failure mode reported in v2 paper.

### 4.12 `references.py`

```python
def validate_citations(manuscript_tex: str, bib_path: Path) -> CitationReport:
    # Bidirectional check:
    #   • every \cite{key} resolves to an entry in .bib
    #   • every .bib entry is cited at least once (else dropped)
    # + Crossref API check on every DOI to verify title+author+year match
    # + LLM-judge anti-hallucination pass: "any of these citations look invented?"
```

Closes the "3 uncited entries in 04a21066" failure + the v2 "40% citation hallucination" finding.

### 4.13 `findings.py`

```python
class FindingsScaffold:
    """Vendored from AI-Research-SKILLs autoresearch.
    5-section structured narrative memory:
      • current_understanding
      • patterns_and_insights
      • lessons_and_constraints
      • open_questions
      • last_direction_decision
    Stored as a MemPalace drawer of kind 'research_findings'.
    """
```

Updated by `meta-analyst` agent at every outer-loop checkpoint. Prevents repeated-failure loops across sessions.

### 4.14 `superpowers_bridge.py`

```python
class WritingPlansBridge:
    def on_plan_written(self, plan_path: Path):
        plugin_palace.archive_plan(plan_path)

class ExecutingPlansBridge:
    def on_skill_start(self, plan_path: Path) -> str:
        return plugin_palace.wake_up(query=plan_path.read_text()[:500], token_budget=2000)
    def on_step_complete(self, step_id, outcome): ...
    def on_skill_complete(self, plan_path, summary): ...
```

Connects the writing-plans / executing-plans / subagent-driven-development skills to the plugin-development palace.

### 4.15 `mempalace_helpers.py`

```python
class PluginPalace(root=Path.home()/".ai-scientist"/"plugin-palace"):
    def archive_spec(self, spec_path, metadata): ...
    def archive_plan(self, plan_path, metadata): ...
    def wake_up(self, query, token_budget): ...
    def search(self, query, limit=5): ...

class ProjectPalace(root=output_dir/".palace"):
    def write_diary(self, agent, content, tags): ...
    def write_findings(self, section, content): ...
    def get_phase_history(self, phase) -> list: ...
```

Wraps the 29 `mcp__mempalace__*` tools into ergonomic Python. Handles ToolSearch loading + error retries internally.

### 4.16 `checkpoints.py`

```python
class CheckpointManager:
    def save(self, phase: str, state: dict):
        # pickle state to <output_dir>/.checkpoints/phase_<phase>.pkl
        # AND mirror to MemPalace as drawer under 'phase-checkpoints' room
    def load(self, phase: str) -> dict | None: ...
    def latest(self) -> str: ...  # name of most recent completed phase
```

Closes the "lost work mid-pipeline" gap. `--resume` flag re-loads from latest.

## 5. Phase-by-phase contract

Each phase now has explicit pre-conditions, the dispatching agent, the Python machinery wrapping it, the post-condition stage gate, and the artifacts produced.

| Phase | Agent (.md template) | Python wrapper | Stage gate | Artifacts |
|---|---|---|---|---|
| -1 Intent | (skill, in-process) | — | — | (in-memory route) |
| 0 Init | (skill, in-process) | `phase_0_init` creates dirs, palace, checkpoints | — | `config.json` |
| 0.5 Ideation | `ideator.md` | `phase_0_5_ideation`: ReflectionLoop → 3 candidates, archived to `idea_candidates.json`, ranked by feasibility×novelty score | gate: ≥3 candidates, all schema-valid | `idea_candidates.json`, `idea.json` (winner) |
| 0.75 Codebase scan | `codebase-scanner.md` | direct dispatch | — | `codebase_analysis.json` |
| 1 Literature | `literature-searcher.md` × 6 sources | `phase_1_literature`: parallel dispatch + dedup + bidirectional metadata validation | gate: ≥10 unique papers OR user-acknowledged sparseness | `paper_list.json`, `references.bib`, `validation_log.json` |
| 2 Hypothesis | `hypothesizer.md` | `phase_2_hypothesis`: ReflectionLoop with hypothesis-quality evaluator | gate: math+methodology+stat-framework all present | `hypothesis.md`, `equations.txt` |
| 3 Codegen | `code-generator.md` | `phase_3_codegen`: ReflectionLoop with `ast.parse()` validation per round, error injection | gate: parses, all imports resolve, smoke-fixture runs | `experiment.py`, `requirements.txt` |
| 4a Experiment | `experiment-runner.md` | existing auto-fix loop, layered-evidence debugging | gate: exit 0, results.csv exists, ≥1 figure | results.csv, .npy, figures/ |
| 4b BFTS | `tree-search-runner.md` | vendored Sakana BFTS, opt-in via `--bfts` | gate: best-node winner promoted | bfts/, results.csv, .npy, figures/ |
| 5.5 Plotting | `plotter.md` | `phase_5_5_plotting`: ReflectionLoop with subprocess error capture, `MAX_FIGURES=12` cap | gate: ≥4 figs, all PNG-valid | `auto_plot_aggregator.py`, refined `figures/` |
| 5 Manuscript | `manuscript-writer.md` (with 6 nested section subagents) | `phase_5_manuscript`: evaluator-optimizer loop with PASS/NEEDS_IMPROVEMENT/FAIL until convergence; LaTeX compile errors injected back | gate: compiles, no `\cite{?}`, all figures referenced, no placeholders | `manuscript.tex` |
| 6 Citations | `citator.md` | `references.py validate_citations` — bidirectional, Crossref-verified, LLM-judge anti-hallucination | gate: 0 dangling cites, 0 uncited entries, 0 LLM-flagged hallucinations | updated `references.bib` |
| 7 Self-review | `reviewer.md` × 3 (positive/negative/neutral bias) | `phase_7_review`: `BiasedReviewers` ensemble, numpy aggregation, outlier flagging | gate: median score recorded, disagreements logged | `review.json`, `manuscript_v2.tex` |
| 8 LaTeX compile | (skill) | direct subprocess; on error → Fixer | gate: PDF produced | `manuscript.pdf` |
| 8.25 Word | (skill) | Pandoc → docx | gate: docx valid | `manuscript.docx` |
| 8.5 VLM review | `vlm-reviewer.md` | `phase_8_5_vlm`: figure dedup pass + per-figure scoring | gate: no high-severity issues OR Fixer cleared | `visual_review.json` |
| 9 Knowledge | (skill, direct MCP) | `phase_9_index`: persist to global knowledge.db + per-job palace | — | jsonl appends, palace drawers |
| 10 Meta-analysis | `meta-analyst.md` | `phase_10_meta`: updates `findings.md` 5-section drawer | — | `meta_analysis.json`, `what_works.json`, findings drawer |
| 11 Slides (NEW) | `slide-presenter.md` (vendored) | `phase_11_slides`: Beamer PDF + python-pptx + speaker notes | gate: pdf + pptx produced | `manuscript-slides.pdf`, `manuscript-slides.pptx` |
| F Fixer | `fixer.md` | superpowers `systematic-debugging` 4-phase: collect logs per layer → compare to last good → form hypothesis → smallest change | up to `fixer_max_rounds_per_phase`, then `AskUserQuestion` | `phase_<N>_failed.json` if all fail |
| CV Cross-validate | `codex-cross-validator.md` | existing — runs after every cross-validatable phase | major_disagree → AskUserQuestion | cross-validation drawer in palace |

## 6. Error handling, retry budget, AskUserQuestion gates

### 6.1 Failure taxonomy

| Failure class | Handler | Action |
|---|---|---|
| API rate limit / transient | `@retry_with_backoff` | Exponential 5 tries, 300s max |
| Schema validation | `extraction.py` + `ReflectionLoop` | Re-prompt with validator's error, max 2 |
| Python AST syntax error | `extract_python` | Re-prompt code-generator with parsing error |
| Experiment timeout/crash | `experiment_loop.py` or BFTS | Auto-fix 3 rounds, then escalate to Fixer |
| Fixer can't recover | `pipeline.py` | `AskUserQuestion`: retry / change scope / accept partial / abort |
| Claude ToS refusal | `codex_bridge` fallback | Re-prompt to Codex; if Codex fails, escalate to user |
| Cross-validation `major_disagree` | `codex-cross-validator` | 4-option `AskUserQuestion` |
| Token budget at 80% | `tokens.py` | Warn user. At 100%: pause + ask |
| Reviewers disagree >1.5σ | `ensemble.py` | Ask user: median / strictest / show all |
| Pipeline-level deadlock | `ReflectionLoop` | Accept best-so-far + log; never block |

### 6.2 The 14 AskUserQuestion gates

Active when `interactivity ≥ "checkpoints"`. Settings:
- `none` — 0 gates (CI / smoke)
- `checkpoints` — 6 critical gates (#1, #2, #7, #9, #11, #15)
- `full` — all 14 gates

| # | Gate | Where | Question |
|---|---|---|---|
| 1 | Intent disambiguation | Phase −1 | "Your request maps to multiple intents. Which fits best?" |
| 2 | **Idea selection from candidates** | Phase 0.5 | "3 candidate ideas generated. Pick one, refine top, or generate more?" |
| 3 | Ideation novelty refinement | Phase 0.5 | "Found N closely-related papers. Pivot to angle X, Y, or keep as-is?" |
| 4 | Literature coverage check | After Phase 1 | "Found N papers across M sources. Coverage looks {good/sparse}. Proceed or expand search?" |
| 5 | Hypothesis pivot | Phase 2 | "Hypothesis OK as drafted, or pivot toward [alternate angle]?" |
| 6 | Code review before run | After Phase 3 | "Code generated. Review it before running, or proceed to experiment?" |
| 7 | **Experiment results acceptance** | After Phase 4 | "Experiment complete with N anomalies. Accept, retry with adjusted params, or troubleshoot?" |
| 8 | Manuscript section selection for revision | After Phase 5 evaluator | "Sections {X,Y} flagged. Revise both, just X, or accept as-is?" |
| 9 | **Reviewer disagreement** | Phase 7 | "Reviewers disagree on {scores}. Use median, adopt strictest, or show all?" |
| 10 | Codex cross-validation `major_disagree` | After any cross-validatable phase | "Codex disagrees on {phase}. Adopt Codex / keep Claude / merge / re-run?" |
| 11 | Fixer escalation | On exhausted Fixer rounds | "Fixer exhausted retries. {options}" |
| 12 | Token budget at 80% | Any phase | "$X budget approached ($Y/$X spent). Continue, downgrade models, or stop?" |
| 13 | Resume vs fresh start | Phase 0 if checkpoint exists | "Prior incomplete job for this topic. Resume from checkpoint, or start fresh?" |
| 14 | Pipeline deadlock | On `ReflectionLoop` no-convergence | "Phase X failed to converge after N rounds. Accept best, retry stronger model, or abort?" |
| 15 | Final acceptance | After Phase 8.5 | "Pipeline complete. Score: X/10. Accept, request revisions, or extract subset?" |

### 6.3 BLOCKED decision tree (per superpowers)

```
agent returns status=BLOCKED:
  ├── reason: "needs more context" → orchestrator extracts from disk/MCP, re-dispatch same model
  ├── reason: "needs harder reasoning" → escalate to next-tier model (sonnet→opus, opus→opus+max thinking)
  ├── reason: "task too large" → break into sub-tasks via meta-agent, re-dispatch each
  └── reason: "fundamentally stuck" → AskUserQuestion gate
Max 2 escalation cycles. Then surface to user.
Never silently retry the same model on the same prompt.
```

## 7. Plan persistence + superpowers integration

### 7.1 Two MemPalace scopes

| Palace | Path | Contents | Lifetime |
|---|---|---|---|
| **Plugin-development** | `~/.ai-scientist/plugin-palace/` | Design specs, implementation plans, gap analyses, dev decisions | Plugin lifetime (across all jobs) |
| **Per-project** | `<output_dir>/.palace/` | Job-specific research plans, hypothesis evolution, agent diaries, cross-validation results, token reports, phase checkpoints | One research job |

### 7.2 Plugin-development palace structure

```
plugin-palace/
├── wing: design
│   ├── room: specs       → drawers: each docs/specs/*.md
│   ├── room: plans       → drawers: each docs/plans/*.md
│   └── room: audits      → drawers: gap analyses, parity checks, OSS surveys
├── wing: decisions
│   ├── room: model-pinning  → drawers: opus/sonnet rationale, gpt-5.5 vs gpt-5.4
│   ├── room: architecture   → drawers: Approach B' decision, prose→Python rewrite
│   └── room: tradeoffs      → drawers: every "why we picked X over Y"
└── wing: journal
    └── room: dev-history → drawers: chronological commit summaries, lessons
```

### 7.3 Per-project palace extends existing structure

```
<output_dir>/.palace/
├── wing: project-{job_id}
│   ├── room: research-plan      → ideation candidates, hypothesis evolution
│   ├── room: phase-checkpoints  → mirrors .checkpoints/*.pkl
│   ├── room: cross-validation   → every Codex cross-val result
│   ├── room: agent-diaries      → per-agent rolling summary
│   ├── room: token-budget       → per-phase token+USD spend
│   └── room: research-findings  → 5-section drawer (current_understanding, patterns_and_insights, lessons_and_constraints, open_questions, last_direction_decision)
```

### 7.4 superpowers integration — three new wires

1. **`writing-plans` skill auto-mines to plugin-palace** via PostToolUse hook on `Write` matching `docs/{specs,plans}/*.md`. Hook calls `mcp/scripts/plan_archive.py mine`.
2. **`executing-plans` skill recall + diary** via `superpowers_bridge.ExecutingPlansBridge`:
   - on_skill_start: `mempalace_wake_up` with plan content as semantic query
   - on_step_complete: `mempalace_diary_write` with step outcome + tags
   - on_skill_complete: final `mempalace_mine` with summary
3. **`subagent-driven-development` skill task search** via `superpowers_bridge.SubagentDrivenBridge`:
   - before dispatch: `mempalace_search` for prior similar implementations
   - after dispatch: write task status to `wing: journal / room: dev-history`

### 7.5 New file: `mcp/scripts/plan_archive.py`

```bash
python plan_archive.py mine \
  --path docs/specs/2026-04-27-orchestrator-rewrite-design.md \
  --palace ~/.ai-scientist/plugin-palace \
  --wing design --room specs \
  --tags auto,plan,2026-04-27
```

Wraps the `mempalace_add_drawer` MCP tool so the PostToolUse hook can call it from Bash.

### 7.6 PostToolUse hook: `hooks/superpowers-plan-mine.sh`

```bash
#!/usr/bin/env bash
PLAN_PATH=$CLAUDE_HOOK_TOOL_INPUT_FILE
[[ "$PLAN_PATH" =~ docs/(plans|specs)/.*\.md$ ]] || exit 0
python "${CLAUDE_PLUGIN_ROOT}/mcp/scripts/plan_archive.py" mine \
  --path "$PLAN_PATH" \
  --palace "$HOME/.ai-scientist/plugin-palace" \
  --wing "design" \
  --room "$(echo "$PLAN_PATH" | grep -oE 'specs|plans')" \
  --tags "auto,plan,$(date +%Y-%m-%d)"
```

Registered in `hooks/hooks.json` under `PostToolUse.matcher: "Write"`.

## 8. AI-Research-SKILLs integrations (4 vendored assets)

Per the investigation: skip the 86 vendor-doc skills (covered by mcp__context7 + mcp__searchcode); skip the autoresearch orchestrator (conflicts with our pipeline); vendor 4 specific assets.

### 8.1 `research-state.yaml` schema

Vendored from `0-autoresearch-skill/templates/research-state.yaml`. Stored at `mcp/templates/research-state-schema.yaml`. `pipeline.py::render_research_state_view()` writes a rendered VIEW to `<output_dir>/research-state.yaml` after each phase. **MemPalace stays canonical**; this is a human-readable mirror.

### 8.2 `findings.md` 5-section scaffold

Vendored as a MemPalace drawer template (`drawer_kind: research_findings`). Sections: current_understanding / patterns_and_insights / lessons_and_constraints / open_questions / last_direction_decision. Updated by `meta-analyst` agent at every outer-loop checkpoint.

### 8.3 Citation-hallucination discipline

Vendored from `20-ml-paper-writing/ml-paper-writing/SKILL.md`. The "40% LLM citation error rate, mandatory programmatic Semantic Scholar / arXiv / CrossRef BibTeX fetch, mark unverifiable as `\cite{PLACEHOLDER_…}`" paragraph ported into `agents/citator.md` + `agents/manuscript-writer.md` as a hard `verification-before-completion` gate.

### 8.4 New agent `slide-presenter.md`

Vendored from `20-ml-paper-writing/presenting-conference-talks/SKILL.md`. Rewritten into our subagent format with declared `tools: Read, Write, Bash`. Runs after Phase 7 (reviewer accepts), produces:
- `manuscript-slides.pdf` (Beamer)
- `manuscript-slides.pptx` (python-pptx, editable)
- speaker notes embedded

### 8.5 (Optional) 3 visual-style presets

From `20-ml-paper-writing/academic-plotting/SKILL.md`. Three named architecture-diagram styles ("Hand-Drawn Sketch" / "Modern Minimal" / "Illustrated Technical") ported into `agents/plotter.md` as opt-in for architecture figures (not data plots). Uses Gemini 3 Pro Image Preview API.

## 9. Testing strategy

### 9.1 Tier 1 — Unit tests (no LLM, ~10s)

| Test file | Covers |
|---|---|
| `tests/test_decorators.py` | `@retry_with_backoff` (mocked subprocess + RateLimitError); `@track_tokens` |
| `tests/test_extraction.py` | `extract_json` (10 fixtures); `extract_python` (AST validation); `extract_latex` |
| `tests/test_convergence.py` | `SemanticConvergence.is_converged` for each signal phrase |
| `tests/test_schemas.py` | `jsonschema.validate` round-trips |
| `tests/test_tokens.py` | `TokenTracker.add`, `.report()`, `.warn_if_over_budget()`, USD conversion |
| `tests/test_status.py` | `AgentStatus` enum + `BLOCKED` decision tree |
| `tests/test_fewshot.py` | `FewShotInjector.inject` produces correctly-formatted XML blocks |
| `tests/test_references.py` | bidirectional `\cite{}` ↔ `.bib`; Crossref mock |
| `tests/test_checkpoints.py` | pickle/unpickle of journal+stage_history+config |
| `tests/test_stage_gate.py` | `stage_progress_eval_spec` parser; block-on-`ready=false` |
| `tests/test_findings.py` | 5-section drawer schema |
| `tests/test_superpowers_bridge.py` | mocked mempalace calls |

CI gate: every PR.

### 9.2 Tier 2 — Static + integration tests (~30s)

| Test | Covers |
|---|---|
| `test_static_checks.py` | All 16 agent files parse (15 existing + new slide-presenter); frontmatter valid |
| `test_routing.py` | 18 routing fixtures still pass |
| `test_pipeline_dry_run.py` | NEW: instantiate `Pipeline()` with mocked dispatch; run `phase_0_5_ideation()` end-to-end with canned candidates; assert ranking + write of `idea_candidates.json` works |
| `test_orchestrator_imports.py` | NEW: every module in `orchestrator/` imports cleanly without LLM access |
| `test_host_detection.py` | `detect_host()` returns expected values for env-var fixtures |
| `test_settings_schema.py` | All settings keys present; defaults validate |

### 9.3 Tier 3 — Live smoke (LLM, ~5–10 min, $2 budget, gated)

```bash
python -m ai_scientist.tests.smoke \
  --topic "linear regression on synthetic data" \
  --domain statistical \
  --interactivity none \
  --token-budget-usd 2.00
```

Asserts:
- `idea_candidates.json` has ≥3 entries (proves multi-candidate ideation)
- `paper_list.json` has ≥10 papers (proves parallel literature)
- `manuscript.tex` has 0 `\cite{?}` errors after consistency pass (proves bidirectional citation)
- `review.json` has ≥3 reviewer entries (proves ensemble)
- `tokens_report.json` totals < $2.00 (proves token tracking + budget enforcement)
- `.checkpoints/phase_*.pkl` exist (proves checkpointing)
- `idea.json` (winner) is one of the candidates (proves selection)
- `manuscript-slides.pdf` exists (proves slide-presenter)

CI gate: nightly only.

### 9.4 Tier 4 — Replay test (canonical Sakana parity, monthly)

Run same topic through:
1. Plugin's Pipeline (Approach B′)
2. Canonical Sakana via `python <plugin>/mcp/lib/sakana/launch_scientist_bfts.py ...`

Compare:
- Idea-quality scores (LLM-as-judge)
- Manuscript-quality scores (LLM-as-judge)
- Time-to-completion ratio (target: plugin ≤ 1.3× Sakana)
- Cost ratio (target: plugin ≤ 1.5× Sakana)

Logged to `tests/regression_log.csv`.

### 9.5 Verification protocol per superpowers' `verification-before-completion`

Before any phase commits its artifact to disk:

```python
@dataclass
class PhaseVerification:
    phase: str
    artifact_paths: list[Path]
    schema_passes: bool
    semantic_checks: list[CheckResult]
    token_usage: dict
    elapsed_seconds: float

def commit_phase(verification: PhaseVerification):
    if not verification.schema_passes:
        raise SchemaError(...)
    failed_checks = [c for c in verification.semantic_checks if c.status == "FAIL"]
    if failed_checks:
        raise QualityGateError(failed_checks)
    # Only now write to disk + checkpoint
```

Phase advancement gated on objective evidence, not LLM self-report.

## 10. Settings additions

```jsonc
{
  "plugins": {
    "ai-scientist": {
      "orchestrator": {
        "use_python_pipeline": true,
        "default_max_reflection_rounds": 5,
        "ideation_num_candidates": 3,
        "review_ensemble_size": 3,
        "review_bias_prompts": ["positive", "negative", "neutral"],
        "fewshot_examples_paths": [
          "${plugin_root}/mcp/templates/fewshot/attention",
          "${plugin_root}/mcp/templates/fewshot/carpe_diem",
          "${plugin_root}/mcp/templates/fewshot/automated_relational"
        ],
        "stage_gate_enabled": true,
        "stage_gate_block_on_failure": true,
        "checkpoint_after_each_phase": true,
        "checkpoint_dir": "${output_dir}/.checkpoints",
        "max_figures": 12,
        "citation_validation": "bidirectional_with_crossref",
        "citation_anti_hallucination_llm_judge": true
      },
      "superpowers": {
        "enabled": true,
        "auto_mine_plans": true,
        "plugin_palace_root": "~/.ai-scientist/plugin-palace",
        "auto_recall_on_session_start": true,
        "wake_up_token_budget": 2000,
        "diary_writes_per_step": true,
        "use_writing_plans_skill": true,
        "use_executing_plans_skill": true,
        "use_subagent_driven_development": true,
        "use_verification_before_completion": true,
        "use_finishing_a_development_branch": true
      },
      "ai_research_skills_vendored": {
        "research_state_view": true,
        "findings_drawer": true,
        "citation_discipline": true,
        "slide_presenter_enabled": true,
        "gemini_diagram_styles": "off"
      }
    }
  }
}
```

## 11. Migration plan (no breakage)

1. **Week 1**: Add `mcp/lib/orchestrator/` modules alongside existing SKILL.md. Pipeline gated behind `orchestrator.use_python_pipeline: false` (default). Existing flow continues.
2. **Week 2**: Feature parity reached. Internal smoke test passes. Flip default to `true` in settings; users on `false` are unaffected.
3. **Week 3**: Vendor AI-Research-SKILLs assets, slide-presenter, plan-persistence hooks. Run replay test.
4. **Week 3 end**: Tag v2.0.0 (semver bump because pipeline behavior changes materially). Old SKILL.md kept in repo at `skills/ai-scientist/SKILL.legacy.md` for users who want to revert.

## 12. Closure: how each audit insufficiency is resolved

| Audit finding | Section that closes it |
|---|---|
| Manuscript factual error (Cohen's d non-monotonic) | §4.7 ensemble reviewers; §6.2 gate #9 |
| 3 uncited bibliography entries | §4.12 references.py bidirectional; §8.3 citation discipline |
| Novelty check skipped | §4.10 phase_0_5 always runs ReflectionLoop with 3 candidates; §6.2 gate #2 forces user pick |
| Confounded fixed lambda | §5 Phase 4b BFTS opt-in for parameter exploration |
| Single-opinion review | §4.7 BiasedReviewers ensemble (positive/negative/neutral) |
| No retries on API blips | §4.1 @retry_with_backoff |
| No token tracking | §4.2 TokenTracker, §6.2 gate #12 budget warning |
| No semantic convergence | §4.5 SemanticConvergence; §4.6 ReflectionLoop |
| No multi-round refinement | §4.6 ReflectionLoop, §5 Phases 0.5/2/3/5/7 |
| No multiple ideation candidates | §5 Phase 0.5, §10 settings.orchestrator.ideation_num_candidates: 3 |
| Few-shot files unused | §4.8 FewShotInjector |
| Crude regex error classification | §4.4 extract_python with AST validation |
| No semantic consistency check | §4.6 evaluator-optimizer in Phase 5 |
| Knowledge index queried only once | §4.15 mempalace_helpers.wake_up between phases |
| BFTS opt-in default | Stays opt-in (per non-goal); §5 Phase 4b documented |
| Weak schema enforcement | §4.3 schemas.py with strict: true + jsonschema.validate |
| No stage-gate progression | §4.11 stage_gate.py |
| No subprocess error injection | §4.6 ReflectionLoop accepts `error_injection=True`; §5 Phases 5/5.5/8 |
| No idea archive diversity | §5 Phase 0.5 archives all candidates, injects as `<previous_ideas>` |
| No VLM duplicate-figure pass | §5 Phase 8.5 explicit dedup pass |
| No checkpointing | §4.16 CheckpointManager + §10 checkpoint_after_each_phase |
| No `MAX_FIGURES` cap | §10 settings.orchestrator.max_figures: 12 |
| No `chktex` LaTeX warnings | §5 Phase 5 LaTeX compile errors injected back via ReflectionLoop |
| No LLM-to-user interactivity | §6.2 14 AskUserQuestion gates |
| Plans/specs not remembered | §7 plugin-palace + superpowers_bridge + plan_archive.py + PostToolUse hook |
| Slow execution | §3.1 Python loop holds state; doesn't re-tokenize per phase |

## 13. Acceptance criteria

The rewrite is considered complete when:

1. All 12 v2 techniques from §4 are reproduced and unit-tested.
2. All 14 AskUserQuestion gates fire as specified when `interactivity = "full"`.
3. Tier 1 + Tier 2 tests all pass (≥150 tests total).
4. Tier 3 smoke test passes within $2 budget on the canonical statistical synthetic test.
5. Tier 4 replay test shows: plugin manuscript-quality LLM-judge score ≥ Sakana's; plugin time-to-completion ≤ 1.3× Sakana's; plugin cost ≤ 1.5× Sakana's.
6. The 4 vendored AI-Research-SKILLs assets (research-state view, findings drawer, citation discipline, slide presenter) all functional.
7. plugin-palace contains this spec + the implementation plan + every commit message from the rewrite.
8. SKILL.md is ≤200 lines (down from ~600).
9. Cross-host parity preserved — same tests pass on Claude Code, Codex CLI, Gemini CLI dispatchers.
10. README updated to reflect the new architecture; v2.0.0 tag pushed.

## 14. Open questions deferred to implementation

- Whether to gate Phase 11 (slide-presenter) on `interactivity="full"` or always run. Default: always run, fast.
- Whether the plugin-palace should be cloud-synced via Anthropic's memory tool. Default: no, local-only.
- Whether to expose `mcp__ai-scientist__cross_validate_phase` as a user-facing MCP tool. Default: internal only.
- BFTS-as-default for `--domain ml` (compute-heavy). Default: stay opt-in, revisit after 10 jobs of usage data.
