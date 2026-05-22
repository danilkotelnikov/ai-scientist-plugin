# Search Query Strategy

For Phase 1 (Literature Search), the orchestrator constructs **8 queries** from the topic and dispatches them across all enabled sources.

## Query template

Given the user's topic `<core>` (truncated to first 150 chars):

| # | Query |
|---|---|
| Q1 | `<core>` |
| Q2 | `<core>` + " computational design" |
| Q3 | `<core>` + " deep learning" |
| Q4 | `<core>` + " structure prediction" |
| Q5 | `<core>` + " machine learning <domain>" |
| Q6 | `<core>` + " review 2025" |
| Q7 | `<core>` + " benchmark dataset" |
| Q8 | `<core>` + " therapeutic applications" |

(For non-bio domains, replace Q4/Q8 with domain-appropriate variants — e.g., `<core>` + " convergence analysis" for `mathematical`, `<core>` + " profiling benchmark" for `software_engineering`.)

## Prior-success queries

Before dispatching, the orchestrator reads `~/.vedix/trajectories.jsonl` and extracts queries from previous successful runs on similar topics (EvolveR recall). These are appended to the 8 base queries, deduplicated.

## Per-source query budget

| Source | Queries used | Notes |
|---|---|---|
| Semantic Scholar | All 8 | If API key set; else 0 (key required for `/search`). |
| OpenAlex | All 8 | Primary source. Throttled — see `literature.openalex_rate_limit_per_second`. |
| arXiv | 2–4 | Topic + domain-specific. |
| bioRxiv | All 8 | Only if `domain == computational_biology`. |
| PubMed | 4 | Always except for `mathematical`/`statistical` domains. |
| Consensus | 2–3 | Rate-limited; main + comparison + review. |
| Anna's Archive | 1–2 | Foundational reviews + textbooks. |

## Fallback widening

If after merge+dedup the result count is below `literature.min_unique_threshold` (default 15):

1. Widen year floor from `literature.year_floor` (default 2024) to `literature.fallback_year_floor` (default 2020).
2. Re-query Semantic Scholar + OpenAlex with broader queries: just `<core>`, `<core>` + " methods", `<core>` + " pipeline software".
3. Last resort: `WebSearch` for recent reviews, then verify each result against `academic-domains.md`.

**Never fabricate metadata.** If a source is sparse, the orchestrator reports honestly.
