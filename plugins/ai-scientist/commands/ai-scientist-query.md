---
description: Search the AI-Scientist persistent knowledge store (papers, hypotheses, benchmarks, claims).
argument-hint: "<search terms>"
---

Invoke the ai-scientist skill in "query knowledge" mode. Use SQLite FTS5 + ChromaDB hybrid search via `mcp__ai-scientist__search_knowledge_index`, then `get_knowledge_details` for top results. Also surface relevant `meta_analysis.json` insights and `what_works.json` recommendations.
