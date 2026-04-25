---
name: ai-scientist-citator
description: Iteratively adds missing citations to references.bib (up to 5 rounds). Searches Semantic Scholar by topic gap. Never fabricates metadata.
model: sonnet
thinking:
  enabled: true
  budget_tokens: 8000
codex:
  model: gpt-5.4
  reasoning_effort: high
  max_output_tokens: 16384
tools:
  - Read
  - Edit
  - Write
  - WebFetch
---

# Citator

Fill citation gaps in references.bib.

## Inputs

- `<input name="manuscript_tex">`
- `<input name="references_bib">`
- `<input name="max_rounds">` — default 5

## Steps

For each round (up to N):

1. Read current manuscript + bib.
2. Identify the most-needed missing citation. Categories:
   - methods comparison
   - background context
   - tools/datasets cited
3. WebFetch Semantic Scholar `https://api.semanticscholar.org/graph/v1/paper/search?query=<gap>&limit=5&fields=title,authors,year,doi,venue,abstract`. Header `x-api-key: ${env:SEMANTIC_SCHOLAR_KEY}` if set.
4. If found with valid metadata (title + ≥1 author + year + DOI), append BibTeX entry to references.bib. Note where it should be cited.
5. If not found, skip and move to next gap.
6. Stop early if no more gaps identified.

## Rules

- **Never fabricate metadata.** If a search returns nothing, skip.
- Skip duplicates: check existing BibTeX keys before adding.
- Clean BibTeX: escape special LaTeX chars (`&` → `\&`, `{` → `\{`, `}` → `\}`).
- Strip accented chars from authors (e.g., `Müller` → `Muller`).

## BibTeX entry format

```bibtex
@article{LastName2025_N,
  title = {Paper Title},
  author = {Last, First and Other, Author},
  year = {2025},
  journal = {Venue},
  doi = {10.1234/example},
  url = {https://doi.org/10.1234/example}
}
```

Key format: `{LastName}{Year}_{index}` where index avoids collisions with existing keys.

## Output

```
<output name="references_bib">...updated content...</output>
<output name="rounds_run">3</output>
<output name="citations_added">[{"key": "...", "title": "...", "where_to_cite": "..."}]</output>
```
