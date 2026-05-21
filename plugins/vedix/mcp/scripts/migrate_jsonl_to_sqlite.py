"""
Migration Script: JSONL → SQLite

Migrates all existing JSONL knowledge store data to the new SQLite backend.
Preserves all existing data while enabling FTS5 full-text search.

Usage:
    python migrate_jsonl_to_sqlite.py [--dry-run] [--skip-chroma]
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def migrate(dry_run: bool = False, skip_chroma: bool = False) -> dict:
    """Migrate JSONL data to SQLite. Returns migration stats."""
    base_dir = Path(os.path.expanduser("~/.ai-scientist"))
    knowledge_dir = base_dir / "knowledge"

    stats = {
        "papers_migrated": 0,
        "hypotheses_migrated": 0,
        "benchmarks_migrated": 0,
        "claims_migrated": 0,
        "triples_migrated": 0,
        "trajectories_migrated": 0,
        "papers_skipped_dup": 0,
        "errors": []
    }

    # Initialize SQLite store
    from sqlite_store import SQLiteKnowledgeStore
    sqlite = SQLiteKnowledgeStore()

    # --- Migrate papers ---
    papers_file = knowledge_dir / "papers.jsonl"
    if papers_file.exists():
        print(f"Migrating papers from {papers_file}...")
        with open(papers_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                    # Normalize: papers may have metadata with title/doi/etc
                    # or have title/abstract as top-level keys
                    meta = raw.get("metadata", {})
                    paper = {
                        "title": raw.get("title", meta.get("title", "")),
                        "authors": raw.get("authors", meta.get("authors", [])),
                        "year": raw.get("year", meta.get("year")),
                        "doi": raw.get("doi", meta.get("doi", "")),
                        "journal": raw.get("journal", meta.get("journal", "")),
                        "url": raw.get("url", meta.get("url", "")),
                        "abstract": raw.get("abstract", meta.get("abstract", "")),
                        "source": raw.get("source", meta.get("source", "")),
                    }
                    # If content is the main field, use it as abstract
                    content = raw.get("content", "")
                    if not paper["abstract"] and content:
                        # Extract abstract: content may be "Title. Authors. Journal. Abstract..."
                        paper["abstract"] = content[:2000]
                    if not paper["title"] and content:
                        # Try to extract title from content (first sentence before period)
                        first_period = content.find(". ")
                        if first_period > 0:
                            paper["title"] = content[:first_period]

                    pid = sqlite.add_paper(paper)
                    if pid:
                        stats["papers_migrated"] += 1
                    else:
                        stats["papers_skipped_dup"] += 1
                except (json.JSONDecodeError, Exception) as e:
                    stats["errors"].append(f"Paper error: {e}")

        print(f"  Migrated {stats['papers_migrated']} papers, "
              f"skipped {stats['papers_skipped_dup']} duplicates")

    # --- Migrate hypotheses ---
    hyps_file = knowledge_dir / "hypotheses.jsonl"
    if hyps_file.exists():
        print(f"Migrating hypotheses from {hyps_file}...")
        with open(hyps_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    hyp = json.loads(line)
                    content = hyp.get("content", "")
                    if content.startswith("[LLM ERROR"):
                        continue  # Skip error entries

                    metadata = hyp.get("metadata", {})
                    sqlite.add_hypothesis(
                        job_id=hyp.get("source_job", ""),
                        content=content,
                        domain="",
                        metadata=metadata
                    )
                    stats["hypotheses_migrated"] += 1
                except (json.JSONDecodeError, Exception) as e:
                    stats["errors"].append(f"Hypothesis error: {e}")

        print(f"  Migrated {stats['hypotheses_migrated']} hypotheses")

    # --- Migrate benchmarks ---
    bench_file = knowledge_dir / "benchmarks.jsonl"
    if bench_file.exists():
        print(f"Migrating benchmarks from {bench_file}...")
        with open(bench_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    bench = json.loads(line)
                    metadata = bench.get("metadata", {})
                    sqlite.add_benchmark(
                        job_id=bench.get("source_job", ""),
                        content=bench.get("content", ""),
                        metadata=metadata
                    )
                    stats["benchmarks_migrated"] += 1
                except (json.JSONDecodeError, Exception) as e:
                    stats["errors"].append(f"Benchmark error: {e}")

        print(f"  Migrated {stats['benchmarks_migrated']} benchmarks")

    # --- Migrate claims ---
    claims_file = knowledge_dir / "claims.jsonl"
    if claims_file.exists():
        print(f"Migrating claims from {claims_file}...")
        with open(claims_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    claim = json.loads(line)
                    sqlite.add_claim(
                        job_id=claim.get("job_id", ""),
                        content=claim.get("content", ""),
                        domain="",
                        word_count=claim.get("word_count"),
                        refs_count=claim.get("refs_count")
                    )
                    stats["claims_migrated"] += 1
                except (json.JSONDecodeError, Exception) as e:
                    stats["errors"].append(f"Claim error: {e}")

        print(f"  Migrated {stats['claims_migrated']} claims")

    # --- Migrate triples ---
    triples_file = knowledge_dir / "triples.jsonl"
    if triples_file.exists():
        print(f"Migrating triples from {triples_file}...")
        with open(triples_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    triple = json.loads(line)
                    sqlite.add_triple(
                        subject=triple.get("subject", ""),
                        predicate=triple.get("predicate", ""),
                        object_=triple.get("object", "")
                    )
                    stats["triples_migrated"] += 1
                except (json.JSONDecodeError, Exception) as e:
                    stats["errors"].append(f"Triple error: {e}")

        print(f"  Migrated {stats['triples_migrated']} triples")

    # --- Migrate trajectories ---
    traj_file = base_dir / "trajectories.jsonl"
    if traj_file.exists():
        print(f"Migrating trajectories from {traj_file}...")
        with open(traj_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    sqlite.add_trajectory(entry)
                    stats["trajectories_migrated"] += 1
                except (json.JSONDecodeError, Exception) as e:
                    stats["errors"].append(f"Trajectory error: {e}")

        print(f"  Migrated {stats['trajectories_migrated']} trajectories")

    # --- Index into ChromaDB (optional) ---
    if not skip_chroma:
        print("\nIndexing into ChromaDB for semantic search...")
        try:
            from chroma_store import ChromaVectorStore
            chroma = ChromaVectorStore()

            if chroma.available:
                # Index papers
                papers = sqlite.conn.execute("SELECT * FROM papers").fetchall()
                docs = []
                for p in papers:
                    p = dict(p)
                    docs.append({
                        "id": f"paper_{p.get('paper_id', '')}",
                        "text": f"{p.get('title', '')} {p.get('abstract', '')} {' '.join(json.loads(p.get('keywords', '[]')))}",
                        "metadata": {
                            "doc_type": "paper",
                            "domain": p.get("domain", ""),
                            "source_job": p.get("source_job", ""),
                            "created_at": p.get("indexed_at", ""),
                        }
                    })
                added = chroma.add_documents_batch(docs)
                print(f"  Indexed {added} papers into ChromaDB")

                # Index hypotheses
                hyps = sqlite.conn.execute("SELECT * FROM hypotheses").fetchall()
                docs = []
                for h in hyps:
                    h = dict(h)
                    docs.append({
                        "id": f"hypothesis_{h.get('hyp_id', '')}",
                        "text": h.get("content", ""),
                        "metadata": {
                            "doc_type": "hypothesis",
                            "domain": h.get("domain", ""),
                            "source_job": h.get("source_job", ""),
                            "created_at": h.get("created_at", ""),
                        }
                    })
                added = chroma.add_documents_batch(docs)
                print(f"  Indexed {added} hypotheses into ChromaDB")

                # Index benchmarks
                benches = sqlite.conn.execute("SELECT * FROM benchmarks").fetchall()
                docs = []
                for b in benches:
                    b = dict(b)
                    docs.append({
                        "id": f"benchmark_{b.get('bench_id', '')}",
                        "text": b.get("content", ""),
                        "metadata": {
                            "doc_type": "benchmark",
                            "domain": "",
                            "source_job": b.get("source_job", ""),
                            "created_at": b.get("created_at", ""),
                        }
                    })
                added = chroma.add_documents_batch(docs)
                print(f"  Indexed {added} benchmarks into ChromaDB")

                print(f"\n  Total ChromaDB documents: {chroma.count()}")
            else:
                print("  ChromaDB unavailable — skipping vector indexing")
                print("  Install with: pip install chromadb")
        except ImportError:
            print("  chromadb not installed — skipping vector indexing")
            print("  Install with: pip install chromadb")

    # Print final stats
    print(f"\n{'='*50}")
    print(f"Migration complete!")
    print(f"{'='*50}")
    for key, value in stats.items():
        if key != "errors":
            print(f"  {key}: {value}")
    if stats["errors"]:
        print(f"\n  Errors ({len(stats['errors'])}):")
        for err in stats["errors"][:5]:
            print(f"    - {err}")
        if len(stats["errors"]) > 5:
            print(f"    ... and {len(stats['errors']) - 5} more")

    sqlite.close()
    return stats


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Migrate JSONL knowledge store to SQLite")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be migrated without doing it")
    parser.add_argument("--skip-chroma", action="store_true", help="Skip ChromaDB indexing")
    args = parser.parse_args()

    migrate(dry_run=args.dry_run, skip_chroma=args.skip_chroma)
