"""
Knowledge Store — Unified Backend

Primary: SQLite with FTS5 full-text search (claude-mem architecture)
Fallback: JSONL append-only files (backward compatible)
Optional: ChromaDB vector embeddings for semantic search

The KnowledgeStore class now delegates to SQLiteKnowledgeStore internally.
All existing API methods are preserved for backward compatibility.
"""

import hashlib
import json
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


class KnowledgeStore:
    """Unified knowledge store: SQLite primary, JSONL fallback, Chroma optional."""

    def __init__(self, base_dir: str = None):
        if base_dir is None:
            base_dir = os.path.expanduser("~/.ai-scientist")
        self.base_dir = Path(base_dir)
        self.knowledge_dir = self.base_dir / "knowledge"
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)

        # Try SQLite backend
        self._sqlite = None
        self._use_sqlite = False
        try:
            from sqlite_store import SQLiteKnowledgeStore
            self._sqlite = SQLiteKnowledgeStore(base_dir=str(self.base_dir))
            self._use_sqlite = True
        except Exception as e:
            print(f"[KnowledgeStore] SQLite unavailable ({e}), using JSONL fallback")
            self._use_sqlite = False

        # Try Chroma vector search
        self._chroma = None
        try:
            from chroma_store import ChromaVectorStore
            self._chroma = ChromaVectorStore(base_dir=str(self.base_dir), auto_install=False)
        except Exception:
            pass

    # --- File paths (for JSONL fallback) ---

    @property
    def papers_file(self):
        return self.knowledge_dir / "papers.jsonl"

    @property
    def hypotheses_file(self):
        return self.knowledge_dir / "hypotheses.jsonl"

    @property
    def benchmarks_file(self):
        return self.knowledge_dir / "benchmarks.jsonl"

    @property
    def claims_file(self):
        return self.knowledge_dir / "claims.jsonl"

    @property
    def triples_file(self):
        return self.knowledge_dir / "triples.jsonl"

    @property
    def trajectories_file(self):
        return self.base_dir / "trajectories.jsonl"

    @property
    def jobs_file(self):
        return self.base_dir / "jobs.json"

    @property
    def meta_analysis_file(self):
        return self.base_dir / "meta_analysis.json"

    @property
    def what_works_file(self):
        return self.base_dir / "what_works.json"

    # --- Read operations ---

    def read_jsonl(self, file_path: Path) -> list:
        """Read all entries from a JSONL file."""
        if not file_path.exists():
            return []
        entries = []
        with open(file_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return entries

    def read_jobs(self) -> dict:
        if not self.jobs_file.exists():
            return {}
        with open(self.jobs_file) as f:
            return json.load(f)

    def read_meta_analysis(self) -> dict:
        if not self.meta_analysis_file.exists():
            return {}
        with open(self.meta_analysis_file) as f:
            return json.load(f)

    def read_what_works(self) -> dict:
        if not self.what_works_file.exists():
            return {}
        with open(self.what_works_file) as f:
            return json.load(f)

    # --- Search operations (SQLite primary, JSONL fallback) ---

    def search_papers(self, query: str, limit: int = 10) -> list:
        """Search papers. Uses FTS5 if SQLite available, else keyword matching."""
        if self._use_sqlite:
            return self._sqlite.search_papers(query, limit=limit)
        return self._search_papers_jsonl(query, limit)

    def _search_papers_jsonl(self, query: str, limit: int) -> list:
        papers = self.read_jsonl(self.papers_file)
        query_terms = self._tokenize(query)
        scored = []
        for paper in papers:
            text = " ".join([
                paper.get("title", ""),
                paper.get("abstract", ""),
                " ".join(paper.get("authors", [])),
                paper.get("source", ""),
                " ".join(paper.get("keywords", []))
            ]).lower()
            score = sum(1 for term in query_terms if term in text)
            if score > 0:
                scored.append((score, paper))
        scored.sort(key=lambda x: -x[0])
        return [p for _, p in scored[:limit]]

    def search_hypotheses(self, query: str, limit: int = 10) -> list:
        """Search hypotheses. Uses FTS5 if SQLite available, else keyword matching."""
        if self._use_sqlite:
            return self._sqlite.search_hypotheses(query, limit=limit)
        return self._search_hypotheses_jsonl(query, limit)

    def _search_hypotheses_jsonl(self, query: str, limit: int) -> list:
        hypotheses = self.read_jsonl(self.hypotheses_file)
        query_terms = self._tokenize(query)
        scored = []
        for hyp in hypotheses:
            text = hyp.get("content", "").lower()
            score = sum(1 for term in query_terms if term in text)
            if score > 0:
                scored.append((score, hyp))
        scored.sort(key=lambda x: -x[0])
        return [h for _, h in scored[:limit]]

    def search_all(self, query: str, mem_type: str = None, limit: int = 10) -> list:
        """
        Search across all knowledge types.

        If ChromaDB is available, uses hybrid search (SQLite filter + Chroma ranking).
        Otherwise uses SQLite FTS5 or JSONL keyword matching.
        """
        # Try Chroma hybrid search first
        if self._chroma and self._chroma.available and query:
            return self._search_hybrid(query, mem_type, limit)

        # Fall back to SQLite/JSONL
        results = []

        if mem_type is None or mem_type == "paper":
            for paper in self.search_papers(query, limit):
                results.append({"type": "paper", "data": paper})

        if mem_type is None or mem_type == "hypothesis":
            for hyp in self.search_hypotheses(query, limit):
                results.append({"type": "hypothesis", "data": hyp})

        if mem_type is None or mem_type == "benchmark":
            if self._use_sqlite:
                benches = self._sqlite.search_benchmarks(query, limit=limit)
            else:
                benches = self.read_jsonl(self.benchmarks_file)
                query_terms = self._tokenize(query)
                benches = [b for b in benches
                           if any(t in b.get("content", "").lower() for t in query_terms)]
            for bench in benches:
                results.append({"type": "benchmark", "data": bench})

        if mem_type is None or mem_type == "claim":
            if self._use_sqlite:
                claims = self._sqlite.search_claims(query, limit=limit)
            else:
                claims = self.read_jsonl(self.claims_file)
                query_terms = self._tokenize(query)
                claims = [c for c in claims
                          if any(t in c.get("content", "").lower() for t in query_terms)]
            for claim in claims:
                results.append({"type": "claim", "data": claim})

        return results[:limit]

    def _search_hybrid(self, query: str, mem_type: str, limit: int) -> list:
        """Hybrid search using ChromaDB for semantic ranking."""
        from chroma_store import HybridSearchEngine
        engine = HybridSearchEngine(self._sqlite, self._chroma)
        raw_results = engine.search(query, mem_type, limit=limit)

        results = []
        for item in raw_results:
            item_type = item.pop("_type", "unknown")
            results.append({"type": item_type, "data": item, "strategy": item.get("_strategy", "hybrid")})

        return results[:limit]

    def query_triples(self, subject: str = None, predicate: str = None,
                      object_: str = None, include_invalid: bool = False) -> list:
        """Query knowledge graph triples."""
        if self._use_sqlite:
            return self._sqlite.query_triples(subject, predicate, object_)
        triples = self.read_jsonl(self.triples_file)
        results = []
        for triple in triples:
            if subject and triple.get("subject") != subject:
                continue
            if predicate and triple.get("predicate") != predicate:
                continue
            if object_ and triple.get("object") != object_:
                continue
            results.append(triple)
        return results

    def get_stats(self) -> dict:
        """Get knowledge store statistics."""
        if self._use_sqlite:
            stats = self._sqlite.get_stats()
            if self._chroma:
                stats["chroma"] = self._chroma.get_stats()
            stats["backend"] = "sqlite_fts5"
            return stats

        return {
            "papers": len(self.read_jsonl(self.papers_file)),
            "hypotheses": len(self.read_jsonl(self.hypotheses_file)),
            "benchmarks": len(self.read_jsonl(self.benchmarks_file)),
            "claims": len(self.read_jsonl(self.claims_file)),
            "triples": len(self.read_jsonl(self.triples_file)),
            "trajectories": len(self.read_jsonl(self.trajectories_file)),
            "jobs": len(self.read_jobs()),
            "backend": "jsonl"
        }

    # --- Progressive disclosure (claude-mem pattern) ---

    def search_index(self, query: str, mem_type: str = None,
                     domain: str = None, limit: int = 20) -> list:
        """
        Layer 1: Get compact index with IDs (~50-100 tokens/result).
        Uses SQLite if available, else JSONL.
        """
        if self._use_sqlite:
            return self._sqlite.search_index(query, mem_type, domain, limit)

        # JSONL fallback: compact results
        results = []
        all_results = self.search_all(query, mem_type, limit)
        for r in all_results:
            data = r["data"]
            results.append({
                "type": r["type"],
                "id": data.get("id", ""),
                "preview": data.get("title", data.get("content", ""))[:100],
                "token_estimate": 60
            })
        return results

    def get_details(self, ids: list, mem_type: str = None) -> list:
        """
        Layer 3: Fetch full details ONLY for filtered IDs.
        Uses SQLite if available, else JSONL scan.
        """
        if self._use_sqlite:
            return self._sqlite.get_details(ids, mem_type)

        # JSONL fallback: scan all files
        details = []
        id_set = set(ids)
        for file_path, type_key in [
            (self.papers_file, "paper"),
            (self.hypotheses_file, "hypothesis"),
            (self.benchmarks_file, "benchmark"),
            (self.claims_file, "claim"),
        ]:
            if mem_type and mem_type != type_key:
                continue
            for entry in self.read_jsonl(file_path):
                if entry.get("id") in id_set:
                    details.append({"type": type_key, **entry})
        return details

    # --- Write operations ---

    def append_jsonl(self, file_path: Path, entry: dict):
        """Append an entry to a JSONL file (for backward compatibility)."""
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def add_paper(self, paper: dict) -> str:
        """Add a paper. Uses SQLite if available, else JSONL."""
        if self._use_sqlite:
            return self._sqlite.add_paper(paper)
        return self._add_paper_jsonl(paper)

    def _add_paper_jsonl(self, paper: dict) -> str:
        doi = paper.get("doi", "").lower()
        if doi:
            existing = self.read_jsonl(self.papers_file)
            for e in existing:
                if e.get("doi", "").lower() == doi:
                    return e.get("id", "duplicate")
        title = paper.get("title", "").lower()[:80]
        if title:
            existing = self.read_jsonl(self.papers_file)
            for e in existing:
                if e.get("title", "").lower()[:80] == title:
                    return e.get("id", "duplicate")

        paper_id = "paper_" + hashlib.md5(
            f"{paper.get('title', '')}{paper.get('doi', '')}".encode()
        ).hexdigest()[:12]

        entry = {
            "id": paper_id,
            "title": paper.get("title", ""),
            "authors": paper.get("authors", []),
            "year": paper.get("year", ""),
            "doi": paper.get("doi", ""),
            "journal": paper.get("journal", ""),
            "url": paper.get("url", ""),
            "abstract": paper.get("abstract", "")[:500],
            "source": paper.get("source", ""),
            "keywords": self._extract_keywords(
                f"{paper.get('title', '')} {paper.get('abstract', '')}"
            ),
            "indexed_at": datetime.now(timezone.utc).isoformat()
        }
        self.append_jsonl(self.papers_file, entry)

        # Also index into Chroma if available
        if self._chroma and self._chroma.available:
            self._chroma.add_document(
                doc_id=paper_id,
                text=f"{paper.get('title', '')} {paper.get('abstract', '')}",
                metadata={"doc_type": "paper", "source": paper.get("source", "")}
            )

        return paper_id

    def add_hypothesis(self, job_id: str, content: str, domain: str,
                       metadata: dict = None) -> str:
        """Add a hypothesis. Uses SQLite if available, else JSONL."""
        if self._use_sqlite:
            return self._sqlite.add_hypothesis(job_id, content, domain, metadata)
        return self._add_hypothesis_jsonl(job_id, content, domain, metadata)

    def _add_hypothesis_jsonl(self, job_id: str, content: str, domain: str,
                               metadata: dict = None) -> str:
        hyp_id = "hypothesis_" + hashlib.md5(
            f"{job_id}{content[:50]}".encode()
        ).hexdigest()[:12]

        entry = {
            "id": hyp_id,
            "content": content[:5000],
            "source_job": job_id,
            "keywords": self._extract_keywords(content),
            "metadata": metadata or {},
            "domain": domain,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        self.append_jsonl(self.hypotheses_file, entry)

        if self._chroma and self._chroma.available:
            self._chroma.add_document(
                doc_id=hyp_id,
                text=content[:10000],
                metadata={"doc_type": "hypothesis", "domain": domain, "source_job": job_id}
            )

        return hyp_id

    def add_benchmark(self, job_id: str, content: str, metadata: dict) -> str:
        """Add a benchmark result. Uses SQLite if available, else JSONL."""
        if self._use_sqlite:
            return self._sqlite.add_benchmark(job_id, content, metadata)
        return self._add_benchmark_jsonl(job_id, content, metadata)

    def _add_benchmark_jsonl(self, job_id: str, content: str, metadata: dict) -> str:
        bench_id = "benchmark_" + hashlib.md5(
            f"{job_id}{datetime.now().isoformat()}".encode()
        ).hexdigest()[:12]

        entry = {
            "id": bench_id,
            "content": content[:500],
            "source_job": job_id,
            "keywords": self._extract_keywords(content),
            "metadata": metadata,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        self.append_jsonl(self.benchmarks_file, entry)
        return bench_id

    def add_triple(self, subject: str, predicate: str, object_: str):
        """Add a knowledge graph triple. Uses SQLite if available, else JSONL."""
        if self._use_sqlite:
            self._sqlite.add_triple(subject, predicate, object_)
        else:
            entry = {
                "subject": subject,
                "predicate": predicate,
                "object": object_,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            self.append_jsonl(self.triples_file, entry)

    def add_trajectory(self, entry: dict):
        """Add a trajectory log entry. Uses SQLite if available, else JSONL."""
        if self._use_sqlite:
            self._sqlite.add_trajectory(entry)
        else:
            entry["timestamp"] = datetime.now(timezone.utc).isoformat()
            self.append_jsonl(self.trajectories_file, entry)

    def update_job(self, job_id: str, updates: dict):
        """Update a job in the registry."""
        jobs = self.read_jobs()
        if job_id in jobs:
            jobs[job_id].update(updates)
        else:
            jobs[job_id] = {"job_id": job_id, **updates}
        with open(self.jobs_file, "w") as f:
            json.dump(jobs, f, indent=2)

    def save_meta_analysis(self, data: dict):
        """Save meta-analysis results."""
        data["last_updated"] = datetime.now(timezone.utc).isoformat()
        with open(self.meta_analysis_file, "w") as f:
            json.dump(data, f, indent=2)

    def save_what_works(self, data: dict):
        """Save what-works recommendations."""
        data["last_updated"] = datetime.now(timezone.utc).isoformat()
        with open(self.what_works_file, "w") as f:
            json.dump(data, f, indent=2)

    def close(self):
        """Close database connections."""
        if self._sqlite:
            self._sqlite.close()

    # --- Utility methods ---

    def _tokenize(self, text: str) -> list:
        """Simple tokenizer for keyword extraction."""
        text = text.lower()
        tokens = re.findall(r'[a-z]+', text)
        stop_words = {
            'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
            'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
            'would', 'could', 'should', 'may', 'might', 'shall', 'can',
            'of', 'to', 'in', 'for', 'on', 'with', 'at', 'by', 'from',
            'as', 'into', 'through', 'during', 'before', 'after', 'and',
            'but', 'or', 'nor', 'not', 'so', 'yet', 'both', 'either',
            'neither', 'each', 'every', 'all', 'any', 'few', 'more',
            'most', 'other', 'some', 'such', 'no', 'only', 'own',
            'same', 'than', 'too', 'very', 'just', 'because', 'if',
            'when', 'where', 'which', 'while', 'who', 'whom', 'what',
            'this', 'that', 'these', 'those', 'it', 'its', 'they',
            'them', 'their', 'we', 'our', 'you', 'your', 'he', 'she',
            'his', 'her', 'i', 'me', 'my'
        }
        return [t for t in tokens if t not in stop_words and len(t) > 2]

    def _extract_keywords(self, text: str, max_keywords: int = 15) -> list:
        """Extract top keywords from text."""
        tokens = self._tokenize(text)
        if not tokens:
            return []
        counter = Counter(tokens)
        return [word for word, _ in counter.most_common(max_keywords)]


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Knowledge store CLI")
    parser.add_argument("command", choices=["stats", "search", "query", "migrate"])
    parser.add_argument("--query", "-q", help="Search query")
    parser.add_argument("--type", "-t", help="Memory type filter")
    parser.add_argument("--limit", "-l", type=int, default=10)
    parser.add_argument("--subject", help="Triple subject")
    parser.add_argument("--predicate", help="Triple predicate")
    parser.add_argument("--object", help="Triple object")
    args = parser.parse_args()

    store = KnowledgeStore()

    if args.command == "stats":
        stats = store.get_stats()
        print(json.dumps(stats, indent=2))

    elif args.command == "search":
        if not args.query:
            print("Error: --query required for search")
            import sys; sys.exit(1)
        results = store.search_all(args.query, args.type, args.limit)
        for r in results:
            strategy = r.get("strategy", "")
            preview = r['data'].get('title', r['data'].get('content', ''))[:100]
            tag = f" [{strategy}]" if strategy else ""
            print(f"[{r['type']}]{tag} {preview}")
        print(f"\nFound {len(results)} results (backend: {stats.get('backend', 'unknown')})")

    elif args.command == "query":
        triples = store.query_triples(args.subject, args.predicate, args.object)
        for t in triples:
            print(f"({t['subject']}) -[{t['predicate']}]-> ({t['object']})")
        print(f"\nFound {len(triples)} triples")

    elif args.command == "migrate":
        from migrate_jsonl_to_sqlite import migrate
        stats = migrate()
        print(f"Migration complete: {json.dumps(stats, indent=2)}")

    store.close()
