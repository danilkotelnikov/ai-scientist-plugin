# Vedix v3.0 — Master Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement each sub-plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Vedix v3.0 — the rebrand of `ai-scientist-plugin` with seven novel rigor tracks, hybrid linguistic register classifier (with full dataset prep + CPU/GPU training scripts), 7 languages first-class, 23 publisher templates bundled at install, multi-provider BYOK across 13 providers including Russian (GigaChat, YandexGPT) and Chinese (DeepSeek, Qwen, Moonshot, Zhipu) families, full Vedix.ai SaaS with all 9 MCPs in Free tier (paid tier = throughput), web UI, VS Code + JetBrains IDE plugins, federated MemPalace, real-time multi-author collab via Yjs CRDT, and pre-print auto-submission to arXiv / bioRxiv / OSF / SSRN.

**Architecture:** Vedix is a cross-host CLI plugin (Claude Code / Codex / Gemini) that orchestrates a multi-agent research pipeline. v3.0 wraps the existing v2.1.x core with a SaaS API layer (FastAPI + Postgres + Redis + hosted MCP fleet) and adds a web UI, IDE plugins, and CRDT collab infrastructure. The seven novel rigor tracks instrument the orchestrator with clean-room independent checks (failure-mode learning, citation graph analytics, counterfactual citation probing, adversarial multi-pass review, semantic revision diff, pre-registration replay, provenance ledger). The hybrid linguistic register classifier ships Layer A (retrieval) + Layer B (fine-tuned mDeBERTa-v3-small on CPU OR xlm-roberta-base on GPU) per (discipline × language) = 56 models. BYOK is a thin abstraction with 13 provider adapters and a configurable fallback chain.

**Tech Stack:**
- Python 3.11+ core (`fastapi`, `pydantic v2`, `uvicorn`, `redis-py`, `asyncpg`)
- LLM clients (`anthropic`, `openai`, `google-generativeai`, `gigachat`, `yandex-cloud`, `dashscope`, `cohere`, `mistralai`)
- ML stack (`torch 2.4+`, `transformers 4.45+`, `safetensors`, `sentence-transformers`, `chromadb`, `datasketch`, `fasttext-langdetect`, `spacy`, `pdfminer.six`, `lxml`)
- LaTeX engines: `pdflatex` for Latin/Cyrillic, `xelatex` for CJK
- Word: `pandoc` 3.x + venue-specific filters
- Web UI: React 19 + TypeScript + TanStack Query + shadcn/ui + react-pdf
- CRDT: Yjs (TypeScript) + y-websocket
- IDE plugins: VS Code Extension API + JetBrains Platform SDK
- Cross-host: existing dispatch layer (`dispatch/{claude_code,codex,codex_native,gemini}.py`)
- MCPs: 9 servers via stdio (Python or Node)
- Payments: ЮKassa + Stripe + CloudPayments webhooks; Boosty; USDT TRC-20

**Spec source:** [`docs/specs/2026-04-30-v3-major-release-spec.md`](../specs/2026-04-30-v3-major-release-spec.md). Marketing brief at [`docs/marketing/2026-05-20-vedix-marketing-brief.md`](../marketing/2026-05-20-vedix-marketing-brief.md). Commercial rebrand at [`docs/specs/2026-04-30-v3-commercial-rebrand-and-monetization.md`](../specs/2026-04-30-v3-commercial-rebrand-and-monetization.md).

---

## Sub-plans (12 blocks)

Each sub-plan is independently executable and produces working, testable software on its own. Execute in dependency order or parallel as the DAG below allows.

| # | Block | Plan file | Effort (weeks) |
|---|---|---|---|
| B1 | Bootstrap + rebrand | [`2026-05-20-block01-bootstrap-and-rebrand.md`](2026-05-20-block01-bootstrap-and-rebrand.md) | 1 |
| B2 | BYOK multi-provider | [`2026-05-20-block02-byok-multi-provider.md`](2026-05-20-block02-byok-multi-provider.md) | 3 |
| B3 | Novel rigor tracks (§4) | [`2026-05-20-block03-novel-rigor-tracks.md`](2026-05-20-block03-novel-rigor-tracks.md) | 5 |
| B4 | Net-new functionality (§5 non-classifier) | [`2026-05-20-block04-net-new-functionality.md`](2026-05-20-block04-net-new-functionality.md) | 3 |
| B5 | Hybrid register discriminator (§5.3) + dataset prep + CPU/GPU training | [`2026-05-20-block05-register-discriminator.md`](2026-05-20-block05-register-discriminator.md) | 5 |
| B6 | 7 languages first-class (§6) | [`2026-05-20-block06-languages.md`](2026-05-20-block06-languages.md) | 4 |
| B7 | 23 publisher templates bundled (§7) | [`2026-05-20-block07-publisher-templates.md`](2026-05-20-block07-publisher-templates.md) | 4 |
| B8 | Vedix.ai SaaS w/ all MCPs free (§8) | [`2026-05-20-block08-saas-vedix-ai.md`](2026-05-20-block08-saas-vedix-ai.md) | 4 |
| B9 | Web UI (§5.7) | [`2026-05-20-block09-web-ui.md`](2026-05-20-block09-web-ui.md) | 3 |
| B10 | IDE plugins — VS Code + JetBrains (§5.8) | [`2026-05-20-block10-ide-plugins.md`](2026-05-20-block10-ide-plugins.md) | 3 |
| B11 | Federated MemPalace + collab + preprint (§§5.9–5.11) | [`2026-05-20-block11-federated-collab-preprint.md`](2026-05-20-block11-federated-collab-preprint.md) | 4 |
| B12 | Polish + launch | [`2026-05-20-block12-polish-and-launch.md`](2026-05-20-block12-polish-and-launch.md) | 2 |
| **Total** | | | **41 weeks** serial |

## Dependency DAG

```
                    B1 (Bootstrap)
                          │
              ┌───────────┴───────────┐
              │                       │
          B2 (BYOK)             B7 (Templates)
              │                       │
        ┌─────┴───┬─────┬─────┐       │
        │         │     │     │       │
       B3        B4    B5    B6       │
     (Rigor)  (NetNew)(Class)(Lang)   │
        │         │     │     │       │
        └────┬────┴─────┴──┬──┴───────┘
             │             │
             └──────┬──────┘
                    │
                B8 (SaaS)
                    │
            ┌───────┼───────┐
            │       │       │
           B9      B10     B11
         (Web)   (IDE)   (Collab)
            │       │       │
            └───────┴───────┘
                    │
                B12 (Launch)
```

**Critical path:** B1 → B2 → B5 → B8 → B11 → B12 = 1 + 3 + 5 + 4 + 4 + 2 = **19 weeks** when fully parallelized.

**With 1 implementer:** 41 weeks serial. **With 2 implementers:** ~22 weeks (B3/B4/B5/B6 parallel after B2; B9/B10/B11 parallel after B8). **With 3 implementers:** ~16 weeks.

## Execution policy

For each sub-plan:

1. Read the sub-plan file end-to-end before starting any task.
2. Follow TDD strictly: write the failing test → run it → implement → run it again → commit. The skill enforces this; do not skip.
3. Mark `- [ ]` checkboxes as you complete each step. Use TodoWrite to track progress at the task level.
4. Commit after every passing test. Frequent commits.
5. After completing a sub-plan, run the full v2.1.x regression suite (`pytest plugins/ai-scientist/mcp/tests/`) to ensure nothing in the carried-over core regressed.
6. When a sub-plan is complete, mark the block done in this master plan's checklist below.

## Master checklist

- [ ] B1: Bootstrap + rebrand
- [ ] B2: BYOK multi-provider
- [ ] B3: Novel rigor tracks
- [ ] B4: Net-new functionality
- [ ] B5: Hybrid register discriminator + dataset prep + training
- [ ] B6: 7 languages first-class
- [ ] B7: 23 publisher templates bundled
- [ ] B8: Vedix.ai SaaS with all MCPs free
- [ ] B9: Web UI
- [ ] B10: IDE plugins
- [ ] B11: Federated + collab + preprint
- [ ] B12: Polish + launch

## Open questions (block until resolved)

From spec §10:

1. Confirm name (default: Vedix)
2. Form-driven setup always-on vs --setup opt-in (default: always-on)
3. Rationale files always-written vs --explain opt-in (default: always-written)
4. Counterfactual probe scope: every citation vs top-cited only (default: every)
5. Adversarial review: 2 passes vs 3 passes (default: 2)
6. Pre-registration: hard-gate vs advisory (default: hard-gate)
7. Solo tier price: 1,290 ₽ vs 990 ₽ (default: 1,290 ₽)
8. Slash command: /vedix only or /vedix + /research alias (default: both)
9. Default BYOK provider chain (default: Anthropic → OpenAI → Google)
10. Web UI ships with v3.0 launch or 4 weeks later as v3.0.1 (default: with launch)

These propagate into B1 (naming), B2 (default provider chain), B3/B4 (rigor defaults), B8 (price), and B9 (Web UI ship timing). The plans assume defaults until told otherwise.
