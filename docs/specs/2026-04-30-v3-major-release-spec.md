# v3.0 Major Release Spec — Vedix

**Date:** 2026-04-30
**Status:** proposal — single major release; no incremental v2.2; supersedes the v2.2 spec at `docs/specs/_superseded/2026-04-30-v2.2-capability-spec-SUPERSEDED.md`
**Trigger:** user direction — "I do not want v2.2 and v3. I want major v3. We cannot copy or take some others ideas like from Imbad0202/academic-research-skills, we must ideate something new."
**Naming:** v3.0 ships under a new commercial name (default recommendation: **Vedix**; see §2). The `ai-scientist-plugin` name is retired at v3.0 cut.
**Independence constraint:** zero copying from `Imbad0202/academic-research-skills`. Where they have solved a problem we also need to solve (integrity gates, claim audit, reviewer anti-anchoring, revision tracking, statistical fallacy detection, AI disclosure), we ship **our own clean-room designs** that are structurally and methodologically different. The novel approaches in §4 are the result.

---

## 1. Goals + non-goals

### 1.1 Goals

v3.0 is one cohesive product release that combines:

1. **Carry-over** of every v2.1.x capability that already works (Python orchestrator, 9 MCPs, cross-host parity, DOI-gated cross-validator, 3-cycle plotter, anti-LLMish Tier 1-4, Codex `spawn_agent` waves, MemPalace persistence).
2. **Six novel rigor tracks** (§4) — independently designed to solve research-pipeline rigor problems without borrowing taxonomy, pattern, or interface from any competitor.
3. **Six net-new capability tracks** (§5) — features neither we nor any competitor currently ship.
4. **Russian-language first-class output** + ГОСТ-7.0.5 + Cyrillic font stack (§6).
5. **Publisher template engine** with LaTeX ↔ Word parity for 6 major venues (§7).
6. **Commercial product layer**: rebrand, BYOK SaaS architecture, RU + global payment rails, marketing plan (§§ 2, 8, 9).

### 1.2 Non-goals (v3.0)

- Multilingual expansion beyond English + Russian (Spanish / German / French / Japanese / Chinese deferred to v3.1).
- Hosted compute (LLM inference on our servers). Stays BYOK.
- Web UI for the orchestrator (CLI + plugin host only; web UI deferred to v3.2).
- VS Code / JetBrains plugin distribution (CLI hosts only at v3.0).
- A trained linguistic classifier on languages other than English + Russian.

---

## 2. Naming + branding

### 2.1 Recommendation (default if you don't override)

**`Vedix`** (Latin script) / **`Ведикс`** (Cyrillic).

- Etymology: Slavic *vědĕti* "to know" + `-ix` software suffix.
- 5 letters, identical pronunciation in EN and RU (/ˈviː.dɪks/ and /ˈvʲe.dʲɪks/).
- Reads as a scholarly software tool, not as an AI product. The "AI" stays in the engine, never in the brand.
- Domain prospects: `vedix.ai`, `vedix.so` likely free; `vedix.com` requires whois confirmation.
- Trademark sweep: no major conflicts in software (class 9) or SaaS (class 42).
- Russian market resonance: the Slavic root makes it feel domestic without sounding parochial in English.

Backup options (only if Vedix fails the trademark sweep):

| Name | Notes |
|---|---|
| **Knowlex** / Нолекс | knowledge + lex; corporate-credible in EN; legal-tech vendor uses it in `.com` |
| **Verax** / Веракс | Latin "truthful"; positions us on rigor/fact-verification (matches our DOI-gate + claim-audit pipeline) |
| **Quaero** / Кверо | Latin "I seek" (etymology of *query*); the EU search project sunset its mark |

### 2.2 Pre-commit checklist (run before any code references the new name)

1. `whois vedix.ai`, `vedix.so`, `vedix.com`
2. USPTO TESS class 9 / class 42 live-marks search containing "Vedix"
3. Rospatent (fips.ru) Russian trademark search for active marks
4. `github.com/vedix` org availability
5. PyPI + npm: `vedix` package availability
6. crates.io + Docker Hub: same

If Vedix fails on any of (1)–(3), fall back to Knowlex; if Knowlex fails, fall back to Verax.

### 2.3 Surface rename (v3.0 cut)

| Surface | v2.1.x | v3.0 |
|---|---|---|
| Repo | `github.com/danilkotelnikov/ai-scientist-plugin` | `github.com/vedix/vedix` (org) |
| Package | `ai-scientist-plugin` | `vedix` (core) + `vedix-claude` / `vedix-codex` / `vedix-gemini` (host adapters) |
| MCP namespace | `mcp__ai-scientist__*` | `mcp__vedix__*` |
| Slash command | `/ai-scientist <topic>` | `/vedix <topic>` (also bound to `/research` as an alias) |
| Domain | none | `vedix.ai` + `vedix.ru` mirror |
| Docs site | repo README | `docs.vedix.ai` |
| Cache path | `~/.claude/plugins/cache/ai-scientist-plugin/...` | `~/.claude/plugins/cache/vedix/...` |
| Data dir | `~/.ai-scientist/` | `~/.vedix/` |

The old `ai-scientist-plugin` repo becomes a deprecation stub with a one-time migration helper that detects `~/.ai-scientist/` and `~/.claude/plugins/cache/ai-scientist-plugin/` and offers to migrate state to `~/.vedix/`. Stub maintained for 6 months.

---

## 3. Architecture overview

v3.0 keeps the v2.1.x foundation intact and layers new modules on top. Total module count rises from 17 to ~30. Cross-host parity (Claude Code + Codex CLI + Gemini CLI) preserved.

```
~/.vedix/
├── repo/                              # canonical clone (cloned by bootstrap)
│   └── plugins/vedix/
│       ├── .claude-plugin/plugin.json
│       ├── agents/                     # 20+ .md agent prompt templates
│       ├── mcp/
│       │   ├── server.py
│       │   ├── lib/
│       │   │   ├── orchestrator/       # 30 Python modules (was 17 in v2.1)
│       │   │   │   ├── # ── carry-over from v2.1 (17 modules) ─────────────
│       │   │   │   ├── status.py, decorators.py, tokens.py, extraction.py,
│       │   │   │   ├── convergence.py, schemas.py, fewshot.py, checkpoints.py,
│       │   │   │   ├── dispatch/{__init__.py,claude_code.py,codex_native.py,codex.py,gemini.py},
│       │   │   │   ├── reflection.py, ensemble.py, stage_gate.py, references.py,
│       │   │   │   ├── findings.py, mempalace_helpers.py, superpowers_bridge.py,
│       │   │   │   ├── pipeline.py, cross_validator.py, source_accounting.py,
│       │   │   │   ├── article_type.py, preflight.py, resource_ledger.py,
│       │   │   │   ├── plotter_loop.py, anti_llm_lint.py, reviewer_ledger.py,
│       │   │   │   ├── # ── new in v3.0 (13 modules) ──────────────────────
│       │   │   │   ├── failure_mode_learning.py     # §4.1 empirical failure taxonomy
│       │   │   │   ├── citation_graph.py            # §4.2 graph analytics over the references network
│       │   │   │   ├── counterfactual_probe.py      # §4.3 citation counterfactual auditing
│       │   │   │   ├── adversarial_review.py        # §4.4 same-reviewer dual-stance protocol
│       │   │   │   ├── semantic_revision_diff.py    # §4.5 embedding-level claim diff
│       │   │   │   ├── prereg_replay.py             # §4.6 pre-registration replay
│       │   │   │   ├── provenance_ledger.py         # §4.7 per-sentence provenance + auto-disclosure
│       │   │   │   ├── prefllight_dialog.py         # §5.1 form-driven research-setup
│       │   │   │   ├── numerical_audit.py           # §5.2 claim ↔ artifact numerical verification
│       │   │   │   ├── register_discriminator.py    # §5.3 retrieval + trained classifier hybrid
│       │   │   │   ├── rationale_writer.py          # §5.4 per-artifact explanatory rationale
│       │   │   │   ├── publisher_engine.py          # §7 LaTeX + Word parity engine
│       │   │   │   └── locale.py                    # §6 RU/EN routing + ГОСТ-7.0.5 citation backend
│       │   │   └── sakana/                          # vendored canonical Sakana (unchanged)
│       │   ├── requirements.txt
│       │   └── .mcp.json
│       ├── settings/
│       ├── scripts/
│       ├── skills/vedix/
│       └── templates/
│           ├── latex/                  # 6 venue templates (§7)
│           ├── word/                   # 6 venue .dotx (§7)
│           └── ai_disclosure/          # auto-disclosure templates per venue
├── palace/                            # MemPalace per-project memory
├── corpus/                            # curated per-discipline papers (§5.3)
│   ├── chemistry/        (150 OA papers, ChromaDB index)
│   ├── biology/          (150)
│   ├── medicine/         (150)
│   ├── physics/          (150)
│   ├── mathematics/      (150)
│   ├── geology/          (150)
│   ├── computer_science/ (150)
│   └── humanities/       (150)
├── classifiers/                       # trained models (§5.3)
│   ├── register_en.safetensors        # XLM-RoBERTa fine-tuned on EN corpus
│   └── register_ru.safetensors        # XLM-RoBERTa fine-tuned on RU corpus
└── knowledge.db                       # global cross-job knowledge store (carry-over)
```

---

## 4. Novel rigor tracks (clean-room independent designs)

These six tracks address problems competing projects also try to solve, but with **structurally and methodologically distinct** approaches. None of these are copied from `Imbad0202/academic-research-skills` or any other source; the designs are derived from first principles below.

### 4.1 Failure-Mode Learning

**Problem:** the pipeline can fail in many ways (hallucinated citations, broken code, shortcut reliance, fabricated methodology, etc.). A static checklist imported from a paper goes stale and may not match our actual failure distribution.

**Imbad's approach (what we are not doing):** import a taxonomy from a published study and check off named modes.

**Our approach:** **Empirical bottom-up taxonomy** derived from our own pipeline's failure history.

Mechanism:
1. Maintain a `~/.vedix/failure_corpus/` directory of historical pipeline runs that the user has marked as "failed in some way" (with `vedix mark-failure <job_id> --description '...'`).
2. A monthly batch (`scripts/learn_failure_modes.py`) clusters failure descriptions using sentence-transformers + HDBSCAN. Each cluster gets a synthetic name + a per-cluster detector function template.
3. The 5–15 most populated clusters become the **active failure-mode set** for the next release. Less-populated clusters live in a "watch list."
4. Each detector in the active set is a small Python function applied at the corresponding pipeline phase; if it fires, the run halts (block) or surfaces (warn) per cluster severity.
5. Failure modes are **versioned** (`failure_modes_v1.json`, `_v2.json`, …). The user sees the version on every run.

Why this is structurally different from any imported checklist:
- The taxonomy is **specific to this pipeline's actual failures**, not a generic research-process taxonomy.
- New failure modes can be added by users marking jobs as failed; the system learns.
- Detector functions are templates the system extends, not hand-curated rules.

Output artifact: `failure_modes.json` per run with the active version, which detectors ran, which fired.

### 4.2 Citation graph analytics

**Problem:** detecting when citations are decorative (don't actually support the surrounding claim), fabricated, or chronologically incoherent.

**Imbad's approach (what we are not doing):** classify each citation into 5 typed HIGH-WARN classes based on text-match heuristics.

**Our approach:** model the manuscript's reference network as a **directed multigraph** and compute graph-analytic signals.

Mechanism:
1. Build a graph G where nodes are paragraphs (~P) and references (~R). Each `\cite{key}` in paragraph p creates a directed edge `p → r`.
2. Compute per-paragraph signals:
   - **Citation density**: edges from this paragraph divided by paragraph word-count. Outliers (very high or very low) are suspicious.
   - **Citation freshness Gini**: distribution of cited-paper publication years; very high concentration in one year is suspicious (suggests cherry-picked corpus).
   - **Venue diversity**: number of unique journals/venues cited; low diversity suggests narrow source pool.
   - **Self-citation ratio**: fraction of citations sharing first-author with the manuscript's declared author list.
   - **Chronology violations**: cited paper's publication date is later than the manuscript draft date (impossible).
   - **Disconnected references**: BibTeX entries with no incoming `→` edge (dangling — never cited).
   - **Decorative citations**: citations within a paragraph whose removal does not change the LLM-judged "claim made by this paragraph." Computed by counterfactual perturbation (see §4.3).
3. Each signal becomes a row in `citation_graph_report.json` with a per-paragraph severity score.
4. The report is consumed by the manuscript-writer's reflection loop: paragraphs flagged for citation-density outliers or decorative citations get rewritten or have citations removed.

Why this is structurally different:
- Graph-theoretic signals (Gini, density, chronology) instead of text-matching classes.
- Computes properties of the **set** of citations, not per-citation labels.
- Decorative-citation detection is the only similar idea, but it is implemented via counterfactual perturbation (§4.3), not fuzzy matching.

Output artifact: `citation_graph_report.json`.

### 4.3 Counterfactual citation probing

**Problem:** detect when a citation is decorative — present for cosmetic credibility, not because it actually supports the claim.

**Imbad's approach (what we are not doing):** fuzzy-match the citation's abstract against the surrounding sentence; if no match, flag.

**Our approach:** **counterfactual perturbation** — replace each citation in turn with a confabulated-but-plausible alternative and ask an LLM-judge whether the surrounding claim still makes sense.

Mechanism:
1. For each `\cite{key}` in the manuscript, generate a "decoy" replacement citation: a confabulated bibliography entry with the same year and a thematically-adjacent title (generated by a small dedicated agent).
2. Render two manuscript variants:
   - **Variant A**: original manuscript.
   - **Variant B**: original manuscript with the citation replaced by the decoy.
3. Dispatch a small LLM-judge with the two variants and ask: "Are these making different claims?"
4. If the answer is "no" — the citation is decorative (the judge couldn't tell the difference, so the cited paper isn't actually doing work).
5. If the answer is "yes" — the citation is load-bearing.

Why this is structurally different:
- Probes whether the citation is **necessary**, not whether the cited content matches.
- Uses synthetic decoys, not external retrieval.
- Yields a binary load-bearing / decorative classification, with the reasoning auditable from the judge's response.

Performance: 1 LLM-judge call per citation. For a 180-citation manuscript: ~3-5 minutes wall-clock at standard rate limits. Caching keyed on (citation_key, paragraph_text) so re-runs are free.

Output artifact: `citation_loadbearing.json` per citation.

### 4.4 Adversarial multi-pass review

**Problem:** reviewers anchor on first impression; a single-pass review is a snapshot, not a robust judgment.

**Imbad's approach (what we are not doing):** blind pre-commitment in Phase 1 before reading the paper.

**Our approach:** **same-reviewer dual-stance protocol** — the same reviewer reviews the paper twice with explicit opposing stances; the verdict is the disagreement between the two.

Mechanism:
1. For each of the 3 biased reviewers (positive, negative, neutral), run two passes:
   - **Pass A**: "Steelman this paper. Find the strongest version of every argument. Argue for acceptance."
   - **Pass B**: given the Pass A review as input, "Break this. Find every weakness Pass A missed. Argue for rejection."
2. The reviewer's published score is the median of Pass A and Pass B Overall scores.
3. The reviewer's **disagreement signal** is the absolute difference. A reviewer with low disagreement is calibrated; with high disagreement is conflicted (the paper has both real strengths and real weaknesses).
4. Aggregate disagreement across the 3 reviewers (mean of three disagreement signals) becomes the **paper's robustness score** — papers with high robustness scores received judgments that survive adversarial probing.

Why this is structurally different from blind pre-commitment:
- No pre-commitment phase. Both passes see the paper.
- The signal is the **gap between two adversarial passes by the same model**, not "the model committed beforehand."
- Captures something different: how much the reviewer's verdict moves under adversarial pressure.

Output artifacts: `adversarial_review.json` (per-reviewer Pass A + Pass B + disagreement) and `paper_robustness.json` (aggregate).

### 4.5 Semantic revision diff

**Problem:** when a manuscript is revised, line-level diff shows what changed textually but not what changed *substantively*. Was a paragraph rewritten or merely rephrased?

**Imbad's approach (what we are not doing):** track which reviewer findings the author *claimed* to address vs. whether the diff actually changed.

**Our approach:** represent each claim as an embedding; compare claim embeddings between revisions.

Mechanism:
1. Extract the set of declarative claims from each revision of the manuscript (using a dedicated `claim_extractor` agent that returns a list of (paragraph_id, claim_text) tuples).
2. Embed each claim with the multilingual-e5 model.
3. Match claims across revisions by paragraph_id + nearest-neighbor in embedding space.
4. For each matched pair, compute cosine similarity:
   - sim > 0.95 → cosmetic rephrase (claim is the same)
   - 0.80–0.95 → minor refinement
   - 0.50–0.80 → substantive revision
   - < 0.50 → claim replaced or removed
5. New claims in the new revision that have no match in the old → additions.
6. Claims in the old revision with no match in the new → deletions.

Why this is structurally different from tracking author-claimed addressings:
- Operates on the actual semantic content, not on the author's narrative about the revision.
- Gives a continuous similarity score, not a yes/no "addressed."
- Surfaces deletions and additions that the author might not call out.

Output artifact: `semantic_revision_diff.json` per `--resume` run.

### 4.6 Pre-registration replay

**Problem:** post-hoc statistical fallacy detection (Simpson's paradox, p-hacking, multiple comparisons, etc.) is a checklist applied after the fact. The honest version is to commit to the statistical analysis plan before running the experiment.

**Imbad's approach (what we are not doing):** an 11-item fallacy checklist applied post-execution.

**Our approach:** **pre-registration replay** — the pipeline emits a pre-registration document before the experiment runs; results audit against the pre-registration; deviations are explicitly flagged as exploratory (not falsified).

Mechanism:
1. After Phase 2 (hypothesis) and before Phase 3 (codegen), the orchestrator emits `prereg.md` containing:
   - The exact hypothesis being tested
   - The primary outcome metric and its expected effect size
   - The statistical test that will be applied (with α, correction method, sample size)
   - The stopping criterion (when do we stop running?)
   - The success criterion (what counts as confirming the hypothesis?)
2. `prereg.md` is committed to the job's MemPalace with a sentinel.
3. After Phase 4 (experiment) and before Phase 5 (manuscript), the pre-reg-replay agent reads `prereg.md` AND `results.csv` AND `experiment_stdout.txt`. For each pre-registered test:
   - Verify the test was actually performed.
   - Verify the test used the pre-registered α and correction.
   - Verify the sample size matches.
   - Verify the stopping criterion was respected (no peeking, no early stop).
   - Verify the success criterion is interpreted as pre-registered.
4. Any test in the results not in the pre-registration → flagged as **exploratory** (an honest research outcome, not a falsification, but distinguishable from the confirmatory result).
5. The manuscript-writer is then constrained: confirmatory results go in the main Results section; exploratory results go in an "Exploratory analyses" subsection with the appropriate hedge ("This analysis was not pre-registered and should be interpreted as hypothesis-generating").

Why this is structurally different:
- Pre-commitment **before** the experiment, not a checklist **after**.
- Doesn't try to detect Simpson's paradox; it makes the analysis plan explicit so the user can see what was and wasn't pre-committed.
- The manuscript prose itself differentiates confirmatory from exploratory — the structural difference is visible in the output.

Output artifacts: `prereg.md`, `prereg_replay.json`, separate Results / Exploratory sections in `manuscript.tex`.

### 4.7 Provenance ledger + auto-disclosure

**Problem:** AI disclosure statements in journal submissions are usually boilerplate. They don't tell the reader which sentence was written by which model with what evidence. Reviewers and editors can't audit the work.

**Imbad's approach (what we are not doing):** venue-specific boilerplate generator.

**Our approach:** **per-sentence provenance ledger** — every sentence in the manuscript is tagged with which agent produced it, what evidence it relied on, how many reflection rounds it survived, which lint tier it passed. The disclosure section is auto-generated from the ledger.

Mechanism:
1. Every agent that contributes to the manuscript (ideator, hypothesizer, manuscript-writer, citator, plotter — for figure captions) writes per-sentence tags to a `provenance.jsonl` log:
   ```json
   {"sentence_id": "intro_3", "agent": "manuscript-writer", "model": "opus-4.7", "evidence": ["Smith2024", "Doe2023"], "reflection_rounds": 2, "lint_tier_passed": 3, "register_discriminator_score": 0.71, "ts": "2026-04-30T12:34:56Z"}
   ```
2. After Phase 5 (manuscript), the `provenance_ledger.py` module reads `provenance.jsonl` and produces:
   - `provenance.html` — color-coded manuscript with per-sentence provenance on hover (for the author's audit)
   - `ai_disclosure.md` — a venue-aware disclosure section with **actual** statistics: "Of N sentences, M (%) were generated by Anthropic Claude Opus 4.7 with median 2 reflection rounds; K (%) were generated by OpenAI GPT-5.5 with median 3 reflection rounds; J (%) were edited by the human author after initial generation."
   - `provenance_summary.json` — machine-readable stats for the venue's required JSON-LD disclosure
3. Per-venue disclosure templates (NeurIPS, ICML, ICLR, ACL, EMNLP, Nature, Science, ACS, Cell) live in `templates/ai_disclosure/{venue}.j2` and the auto-disclosure renders the appropriate template populated with the actual stats.

Why this is structurally different:
- Honest: the disclosure says what actually happened, sentence by sentence.
- Auditable: reviewer can hover any sentence and see provenance.
- Venue-aware boilerplate is just the rendering layer; the substance comes from the ledger.

Output artifacts: `provenance.jsonl`, `provenance.html`, `ai_disclosure.md`, `provenance_summary.json`.

---

## 5. Net-new functionality (independent of any competitor)

### 5.1 Form-driven pre-experimental dialog

New phase `-2` (runs before intent classification). An interactive structured form collects:

1. Research question (free-form)
2. Domain (8 niches; auto-pre-fills domain templates)
3. Article type (review / experimental / benchmark / theoretical / case-study / policy-brief)
4. Target venue (one of the registered venues)
5. Output language(s)
6. Compute budget (max external API requests; max wall-clock)
7. Codebase path (optional)
8. Existing literature corpus (optional — Zotero JSON / folder of PDFs / Obsidian)
9. Author list + ORCID + affiliations
10. Conflict-of-interest declarations
11. Funder acknowledgements

Output: `job_config.json`. Always-on by default; `--no-setup` opts out for scripted callers.

Implementation: cascading `AskUserQuestion` rounds (4 questions per round, 3 rounds = 12 questions).

### 5.2 Post-experiment numerical claim audit

After Phase 5 (manuscript drafting) and before Phase 6 (citations):

1. Parse the manuscript with a LaTeX-aware AST parser.
2. Extract every quantitative claim: numbers, percentages, accuracy / loss / F1 / AUC values, sample sizes.
3. For each claim, locate the source artifact:
   - Table values → `results.csv`
   - Figure caption claims → rendered PNG + figure data
   - Inline numbers → `experiment_stdout.txt`
4. Compute `claim_value` vs `artifact_value`. Tolerance: 1e-3 absolute / 1% relative.
5. Mismatches go into `numerical_audit.json` with `claim`, `claim_value`, `artifact_value`, `artifact_path`, `delta`, `severity`. Block-severity halts; warn surfaces in final summary.

### 5.3 Hybrid linguistic register discriminator (retrieval + trained classifier)

Two layers, both run at runtime in the manuscript-writer's reflection loop.

**Layer A — retrieval-grounded discriminator (always on; no training required).**

1. Per discipline (8 niches), curate ~150 OA papers (English + Russian) into `~/.vedix/corpus/{discipline}/`.
2. Embed paragraph chunks with `intfloat/multilingual-e5-large` into ChromaDB.
3. At runtime, for each manuscript paragraph: embed it, k-NN against the matching discipline's corpus (k=5), score cosine similarity. If max similarity < 0.55, the paragraph reads out-of-register.
4. Dispatch a small LLM-judge with the paragraph + 3 retrieved corpus examples. Judge says: pass / fail-rewrite / fail-rewrite-with-suggestion.
5. Loop: max 2 retries per paragraph.

**Layer B — trained per-discipline + per-language classifier (optional second pass).**

1. Single automated script `scripts/train_register_classifier.py` does the full pipeline:
   - Harvest the corpus (uses MCPs: openalex, semanticscholar, annas-mcp).
   - Generate adversarial "AI-style" negatives by rewriting corpus paragraphs with a generator agent in LLM-ish register (Tier 1+2 blacklist words injected).
   - Fine-tune `xlm-roberta-base` (multilingual) as a binary in-register/out-of-register classifier per discipline.
2. Hardware: must fit Xeon 8368 CPU-only OR RTX 4060 8GB. The script auto-detects available hardware and:
   - **GPU available (RTX 4060 8GB)**: train xlm-roberta-base (270M params) at batch size 4, gradient accumulation 8, fp16. Per-discipline checkpoint ≈ 1.1 GB. Training time per discipline: ~6-10 hours on the 4060.
   - **CPU-only (Xeon 8368)**: train a smaller model — `xlm-roberta-distil` (130M params) or `mDeBERTa-v3-small` — at higher batch size since 512 GB RAM is ample. Per-discipline checkpoint ≈ 500 MB. Training time per discipline: ~18-30 hours on the Xeon. Run all 8 disciplines as a Sunday batch.
3. After training, each discipline gets a `~/.vedix/classifiers/register_{discipline}_{language}.safetensors` file. Classifiers are not bundled in the repo (too large); they are downloaded from `models.vedix.ai` after `vedix model fetch` OR built locally with `vedix model train`.
4. Runtime: classifier inference adds ~30ms per paragraph; gates run in parallel with Layer A. A paragraph that passes BOTH layers proceeds; failing either triggers a rewrite.

This is the **only** v3.0 component that requires training. Layer A works without any training and ships as the v3.0 baseline. Layer B is opt-in via `vedix model train` and Pro-tier users get pre-trained classifiers via `vedix model fetch`.

### 5.4 Per-artifact explanatory rationale files

For every major artifact (manuscript, plots, code, references, hypothesis, idea), the corresponding agent ALSO writes a `<artifact>.rationale.md` companion explaining:

- Why this artifact exists (which research question / hypothesis it serves)
- What decisions the agent made (competing options considered, choice rationale)
- What evidence the agent relied on (papers, numerical values, prior work)
- What the human researcher should verify (3-5 specific check-this items)
- What the agent is uncertain about (open questions, hedges)

Always-on by default; `--no-rationale` opts out.

Implementation: a new `rationale-writer` agent runs after each major phase, consumes the producing agent's decision log + key inputs, writes the markdown file.

### 5.5 Codebase-aware research mode

When `--codebase /path/to/repo` is supplied:

- Phase 0.75 codebase-scanner reads the entire repo, builds a graph of {files, functions, classes, imports}.
- The hypothesis-generator uses the codebase as the grounding source — every hypothesis must reference a specific module / function / data structure in the codebase.
- The experiment-runner can target a specific function as the system under test, not just running arbitrary code.
- The manuscript-writer cites the codebase as a "Software" reference per FORCE11 software citation principles.

### 5.6 Public-result reproducibility audit

For experimental papers, after Phase 8 (compile):

- The audit-agent runs the experiment one more time from clean state (fresh venv, no cached results) in a sandbox.
- Compares the fresh-run numerical results against the manuscript's claimed numbers.
- Flags any irreproducible result with `reproducibility_audit.json` + a `.rationale.md` documenting the divergence (was it stochastic? did the random seed not propagate? was there an off-by-one in the codepath that loaded results?).

---

## 6. Languages

### 6.1 v3.0 scope: English + Russian first-class

- ГОСТ-7.0.5-2008 citation backend (Russian academic style)
- Cyrillic-aware LaTeX templates (`\usepackage[utf8]{inputenc}\usepackage[T2A]{fontenc}` + CMU Serif or Noto Serif)
- Word output: `.dotx` templates with Times New Roman + Liberation Serif fallback for portability
- Russian academic prose register lint: impersonal-passive preference; flag paragraph-initial `Кроме того`, `Более того`, `Также`, `Стоит отметить`, `Важно подчеркнуть`, `Следует отметить`; em-dash budget tuned to 4 / 1k words (Russian uses dashes more liberally than English)
- BibTeX entries preserve original-language orthography (no transliteration)

### 6.2 Deferred to v3.1

- Spanish (`Es`, `Estado del arte`-style register)
- German (DIN 1505 citations)
- French (NF Z44-005)
- Japanese (JIS X 0202)
- Simplified + Traditional Chinese (GB/T 7714 + APA 7.0 CJK)

---

## 7. Publisher template engine

`publisher_engine.py` provides LaTeX + Word output parity for 6 venues at v3.0:

| Venue | LaTeX template | Word template | Citation style | Region |
|---|---|---|---|---|
| Nature / Nature family | `templates/latex/nature/` | `templates/word/nature.dotx` | Nature | global |
| Cell Press | `templates/latex/cell/` | `templates/word/cell.dotx` | Cell | global |
| IEEE / ACM | `templates/latex/ieee/` | `templates/word/ieee.dotx` | IEEE | global |
| ACS journals | `templates/latex/acs/` | `templates/word/acs.dotx` | ACS | global |
| MDPI | `templates/latex/mdpi/` | `templates/word/mdpi.dotx` | MDPI | global |
| ВАК + ДАН generic Russian | `templates/latex/gost-generic/` | `templates/word/gost-generic.dotx` | ГОСТ-7.0.5 | RU |

Parity check: after generating both `manuscript.pdf` and `manuscript.docx`, the publisher engine compares them along:
- Section order
- Section title text
- Number of equations, figures, tables
- Reference count
- Word count (±2%)

Any divergence is flagged in `parity_report.json` for the author to resolve.

CLI: `--venue nature` / `--venue gost-generic` (and so on); default per article-type.

Templates derived from public submission guidelines (no copyrighted content embedded). The `gost-generic` template is generic enough to fit most ВАК-perechen' journals; venue-specific RU journals (DAN RAS, Uspekhi) come later via the `vedix add-venue` plugin point.

Additional v3.1 venues (deferred): Lancet, BMJ, Springer Nature, RSC, Elsevier flagship journals.

---

## 8. Commercial layer (BYOK SaaS)

### 8.1 Product surface

The free-tier plugin (under Vedix branding) covers:
- Python orchestrator + 9 MCPs + cross-host parity
- Layer A retrieval-grounded register discriminator (Russian + English corpora bundled or fetched at first use)
- All 6 novel rigor tracks (§4)
- All 5 net-new functionality tracks (§5)
- Publisher engine with 2 templates (Nature + ГОСТ-generic) bundled; other 4 fetched on first use
- BYOK (user provides Anthropic / OpenAI / Gemini key)

The paid `vedix.ai` SaaS adds:
- Layer B trained classifier (8 disciplines × 2 languages = 16 models pre-trained on our infrastructure; users on Free can train locally, but it costs them compute time)
- Hosted job queue (run jobs without local compute; we manage retries, MCP availability)
- Team shared MemPalace (multi-user research collaboration)
- Audit-log retention (90 days cloud vs 7 days local)
- Priority access to Pro-tier models (vendor-relationship optimizations: GPT-5.5 xhigh, Opus 4.7 at 64k thinking)
- Per-venue paid template packs (more publishers as they're added; the 6 core stay free)

### 8.2 Tier structure

| Tier | RUB/mo | USD/mo | Limits |
|---|---|---|---|
| **Free** | 0 ₽ | $0 | 100% of plugin features; 0 hosted jobs; BYOK only |
| **Solo** | 1,290 ₽ | $14 | 20 hosted jobs / month; 1 user; Layer B classifier (RU + EN); 6 publisher templates |
| **Lab** | 4,900 ₽ | $49 | 200 hosted jobs / month; 5 users; team shared MemPalace; all publisher templates |
| **Institution** | from 24,900 ₽ | from $249 | Unlimited; SSO; on-prem option; SLA |

### 8.3 Payment infrastructure

| Channel | Russia-resident? | Used for |
|---|---|---|
| ЮKassa | ✓ | RUB cards (Mir + Visa/MC) — primary RU rail |
| CloudPayments | ✓ | RUB cards — backup rail |
| Stripe | ✗ (RU cards) | Global cards (USD/EUR) — primary non-RU rail |
| Boosty | ✓ | Recurring micro-subs from RU patrons |
| Crypto (USDT TRC-20) | ✓ | Last-resort for sanctions-affected users |

Legal entity: **ИП-USN-6%** registered through Tinkoff (one-day online registration). Suitable up to 60M ₽/year revenue. Above that, migrate to ООО.

### 8.4 Marketing plan (Russia)

- **Habr.com** long-form release post (Russian) — technical deep-dive on the cross-host pipeline, including a ГОСТ-output demo
- **vc.ru** startup-announcement post for the v3.0 launch
- **Telegram channels**: `@nplusonemag`, `@neural_machine`, `@datasciencegroup`, `@papers_we_love_rus`
- **University outreach**: HSE / MIPT / Skoltech direct seminar invitations
- **Habr series**: "Building an autonomous research pipeline" — 6 posts, one per subsystem (DOI gate, anti-LLMish lint, Codex spawn_agent waves, register discriminator, etc.)
- **YouTube channel**: weekly research-job walkthroughs

### 8.5 Marketing plan (global)

- **Hacker News** Show HN post on v3.0 launch
- **Twitter/X** thread with the same content as the Habr post (English)
- **arXiv blog post** (we publish a methods-paper on the pipeline itself, hosted on arXiv)
- **NeurIPS / ICML demo track** submissions for the 2026 cycle

---

## 9. Timeline + phasing

Single major release. No incremental v2.2; v2.1.2 is the last v2.x.

| Block | Weeks | Tracks |
|---|---|---|
| **Bootstrapping** | 1 | Repo rename, package rename, MCP namespace rename, migration helper, deprecation stub |
| **Novel rigor tracks** | 4 | §4.1 failure-mode learning, §4.2 citation graph, §4.3 counterfactual probe, §4.4 adversarial review, §4.5 semantic diff, §4.6 prereg replay, §4.7 provenance ledger |
| **Net-new functionality** | 3 | §5.1 setup dialog, §5.2 numerical audit, §5.3 register discriminator (Layer A only), §5.4 rationale files, §5.5 codebase-aware, §5.6 reproducibility audit |
| **Languages + publisher engine** | 3 | §6 RU first-class, §7 6 venue templates with parity check |
| **Trained classifier (Layer B)** | 3 | §5.3 corpus curation, single automated training script, distribution mechanism |
| **Commercial layer** | 2 | `vedix.ai` SaaS scaffolding, ЮKassa + Stripe integration, tier-gating, hosted job queue |
| **Polish + launch** | 2 | Habr post, vc.ru post, docs site, demo videos, smoke testing |
| **Total** | **18 weeks** (~4.5 months) | full v3.0 release |

Parallelizable down to ~12 weeks with 2 implementers; ~9 weeks with 3.

---

## 10. Open questions for the user

To unblock v3.0:

| # | Question | Default if you don't choose |
|---|---|---|
| 1 | Confirm name: **Vedix** (recommended), Knowlex, Verax, Quaero, or other? | Vedix |
| 2 | Form-driven setup: always-on or `--setup` opt-in? | always-on |
| 3 | Rationale files: always-written or `--explain` opt-in? | always-written |
| 4 | Layer B trained classifier: train locally on user's hardware, or bundle pre-trained models in Pro-tier? | both — Free trains locally, Pro gets pre-trained |
| 5 | Counterfactual citation probe: run on every citation (default) or only top-cited (≥3 reuses; cheaper)? | every citation (~3-5 min for 180 cites) |
| 6 | Adversarial review: 2 passes per reviewer (default) or 3 passes (steelman / break / re-steelman)? | 2 passes |
| 7 | Pre-registration: hard-gate the experiment (must commit to prereg before running) or advisory (warn if prereg missing)? | hard-gate |
| 8 | Solo tier price: 1,290 ₽ or lower (990 ₽)? | 1,290 ₽ |
| 9 | Slash command: `/vedix <topic>` only, or both `/vedix` + `/research` alias? | both |
| 10 | Russian publisher template scope: «ГОСТ-generic» only (covers most ВАК journals) or add specific venues (DAN RAS, Uspekhi)? | gost-generic only at v3.0; specific RU venues at v3.1 |

All ten are defaults-locked. Pick the subset you want to override; the rest stay as recommended.

---

## 11. Out of scope (v3.1 and later)

- Multilingual expansion beyond EN + RU (Spanish, German, French, Chinese, Japanese)
- Web UI for the orchestrator
- VS Code / JetBrains plugin distribution
- Hosted LLM inference (we stay BYOK)
- Specific RU publisher templates beyond `gost-generic` (DAN RAS, Uspekhi, specific institutional templates)
- Mobile app
- Cross-organization shared MemPalace / federated knowledge graph
- Pre-print server integration (auto-submit to arXiv / bioRxiv / OSF on completion)
- Real-time collaboration in the orchestrator (multiple authors editing concurrently)
