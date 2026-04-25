"""
ChromaDB Vector Search Integration

Adapted from claude-mem's ChromaSync architecture:
- ChromaDB for semantic vector embeddings
- Hybrid search: SQLite metadata filter + Chroma semantic ranking
- Graceful fallback when Chroma is unavailable
- Auto-installation of chromadb package

This provides true semantic search across papers, hypotheses, and benchmarks.
"""

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional


class ChromaVectorStore:
    """ChromaDB-backed vector search for semantic knowledge retrieval."""

    def __init__(self, base_dir: str = None, auto_install: bool = True):
        if base_dir is None:
            base_dir = os.path.expanduser("~/.ai-scientist")
        self.base_dir = Path(base_dir)
        self.persist_dir = self.base_dir / "knowledge" / "chroma_db"
        self.persist_dir.mkdir(parents=True, exist_ok=True)

        self._client = None
        self._collection = None
        self._available = False
        self._auto_install = auto_install

        self._init_chroma()

    def _init_chroma(self):
        """Initialize ChromaDB client."""
        try:
            import chromadb
            self._client = chromadb.PersistentClient(
                path=str(self.persist_dir)
            )
            self._collection = self._client.get_or_create_collection(
                name="ai_scientist_knowledge",
                metadata={"hnsw:space": "cosine"}
            )
            self._available = True
        except ImportError:
            if self._auto_install:
                if self._install_chromadb():
                    self._init_chroma()  # Retry after install
                else:
                    self._available = False
            else:
                self._available = False
        except Exception as e:
            print(f"[ChromaVectorStore] Init failed: {e}")
            self._available = False

    def _install_chromadb(self) -> bool:
        """Attempt to install chromadb package."""
        print("[ChromaVectorStore] chromadb not found, attempting install...")
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "chromadb", "-q"],
                check=True, capture_output=True, timeout=120
            )
            print("[ChromaVectorStore] chromadb installed successfully")
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            print(f"[ChromaVectorStore] Failed to install chromadb: {e}")
            return False

    @property
    def available(self) -> bool:
        return self._available

    def add_document(self, doc_id: str, text: str, metadata: dict = None) -> bool:
        """Add a document to the vector store."""
        if not self._available:
            return False

        try:
            # Generate a unique embedding ID
            embedding_id = hashlib.md5(doc_id.encode()).hexdigest()[:16]

            doc_metadata = {
                "doc_id": doc_id,
                "doc_type": metadata.get("doc_type", "unknown"),
                "domain": metadata.get("domain", ""),
                "source_job": metadata.get("source_job", ""),
                "created_at": metadata.get("created_at", ""),
            }

            # Chroma has a character limit per document, truncate if needed
            max_chars = 65000
            text = text[:max_chars] if text else "empty"

            self._collection.upsert(
                ids=[embedding_id],
                documents=[text],
                metadatas=[doc_metadata]
            )
            return True
        except Exception as e:
            print(f"[ChromaVectorStore] Failed to add document: {e}")
            return False

    def add_documents_batch(self, documents: list) -> int:
        """Add multiple documents at once. Returns count added."""
        if not self._available:
            return 0

        ids = []
        texts = []
        metadatas = []

        for doc in documents:
            doc_id = doc.get("id", doc.get("doc_id", ""))
            text = doc.get("text", doc.get("content", ""))
            metadata = doc.get("metadata", {})

            embedding_id = hashlib.md5(doc_id.encode()).hexdigest()[:16]
            ids.append(embedding_id)
            texts.append(text[:65000] if text else "empty")
            metadatas.append({
                "doc_id": doc_id,
                "doc_type": metadata.get("doc_type", "unknown"),
                "domain": metadata.get("domain", ""),
                "source_job": metadata.get("source_job", ""),
                "created_at": metadata.get("created_at", ""),
            })

        try:
            self._collection.upsert(
                ids=ids,
                documents=texts,
                metadatas=metadatas
            )
            return len(ids)
        except Exception as e:
            print(f"[ChromaVectorStore] Batch add failed: {e}")
            return 0

    def search(self, query: str, limit: int = 20,
               doc_type: str = None, domain: str = None) -> list:
        """
        Semantic search using ChromaDB.

        Returns list of results with doc_id, distance, and metadata.
        This is Layer 1 of the progressive disclosure workflow.
        """
        if not self._available or not query:
            return []

        try:
            where_filter = {}
            if doc_type:
                where_filter["doc_type"] = doc_type
            if domain:
                where_filter["domain"] = domain

            kwargs = {
                "query_texts": [query],
                "n_results": min(limit * 3, 100),  # Get more for filtering
            }
            if where_filter:
                kwargs["where"] = where_filter

            results = self._collection.query(**kwargs)

            # Format results
            # Chroma returns nested lists: ids=[[...]], metadatas=[[...]], distances=[[...]]
            formatted = []
            ids_list = results.get("ids", [[]])
            metadatas_list = results.get("metadatas", [[]])
            distances_list = results.get("distances", [[]])

            # Handle both nested and flat formats
            if ids_list and isinstance(ids_list[0], list):
                ids_flat = ids_list[0]
                metadatas_flat = metadatas_list[0] if metadatas_list else []
                distances_flat = distances_list[0] if distances_list else []
            else:
                ids_flat = ids_list
                metadatas_flat = metadatas_list
                distances_flat = distances_list

            for i, doc_id in enumerate(ids_flat):
                meta = metadatas_flat[i] if i < len(metadatas_flat) else {}
                distance = distances_flat[i] if i < len(distances_flat) else None

                formatted.append({
                    "doc_id": meta.get("doc_id", "") if meta else "",
                    "doc_type": meta.get("doc_type", "") if meta else "",
                    "domain": meta.get("domain", "") if meta else "",
                    "source_job": meta.get("source_job", "") if meta else "",
                    "distance": distance,
                    "score": 1 - distance if distance else 0,
                })

            return formatted[:limit]

        except Exception as e:
            print(f"[ChromaVectorStore] Search failed: {e}")
            return []

    def delete_document(self, doc_id: str) -> bool:
        """Delete a document from the vector store."""
        if not self._available:
            return False

        try:
            embedding_id = hashlib.md5(doc_id.encode()).hexdigest()[:16]
            self._collection.delete(ids=[embedding_id])
            return True
        except Exception as e:
            print(f"[ChromaVectorStore] Delete failed: {e}")
            return False

    def count(self) -> int:
        """Get total document count."""
        if not self._available:
            return 0
        try:
            return self._collection.count()
        except Exception:
            return 0

    def get_stats(self) -> dict:
        """Get vector store statistics."""
        return {
            "available": self._available,
            "document_count": self.count(),
            "persist_path": str(self.persist_dir)
        }


class HybridSearchEngine:
    """
    Hybrid search combining SQLite FTS5 + ChromaDB vector search.

    Follows claude-mem's HybridSearchStrategy pattern:
    1. SQLite metadata filter (get all IDs matching criteria)
    2. Chroma semantic ranking (rank by relevance)
    3. Intersection (keep only IDs from step 1, in rank order from step 2)
    4. Return results in semantic rank order
    """

    def __init__(self, sqlite_store=None, chroma_store=None):
        from sqlite_store import SQLiteKnowledgeStore
        self.sqlite = sqlite_store or SQLiteKnowledgeStore()
        self.chroma = chroma_store or ChromaVectorStore()

    def search(self, query: str, mem_type: str = None,
               domain: str = None, limit: int = 20) -> list:
        """
        Hybrid search: SQLite filter + Chroma ranking.

        If Chroma is available:
        1. Get SQLite metadata matches
        2. Get Chroma semantic matches
        3. Intersect, keeping Chroma's rank order

        If Chroma is unavailable:
        Fall back to SQLite FTS5 only.
        """
        if not query:
            return []

        if self.chroma.available:
            return self._hybrid_search(query, mem_type, domain, limit)
        else:
            return self._sqlite_fallback(query, mem_type, domain, limit)

    def _hybrid_search(self, query: str, mem_type: str,
                       domain: str, limit: int) -> list:
        """Hybrid search with Chroma ranking."""
        results = []

        for type_name in self._get_types(mem_type):
            # Step 1: SQLite metadata filter
            sqlite_ids = self._get_sqlite_ids(type_name, domain)

            if not sqlite_ids:
                continue

            # Step 2: Chroma semantic ranking
            chroma_results = self.chroma.search(
                query,
                limit=len(sqlite_ids),
                doc_type=type_name,
                domain=domain
            )

            # Step 3: Intersect - keep only SQLite IDs, in Chroma rank order
            chroma_doc_ids = [r["doc_id"] for r in chroma_results]
            ranked_ids = self._intersect_with_ranking(sqlite_ids, chroma_doc_ids)

            # Step 4: Hydrate from SQLite in semantic rank order
            if ranked_ids:
                details = self._hydrate(type_name, ranked_ids[:limit])
                results.extend(details)

        return results[:limit]

    def _sqlite_fallback(self, query: str, mem_type: str,
                         domain: str, limit: int) -> list:
        """Fallback to SQLite FTS5 only."""
        results = []

        for type_name in self._get_types(mem_type):
            if type_name == "paper":
                items = self.sqlite.search_papers(query, domain, limit=limit)
            elif type_name == "hypothesis":
                items = self.sqlite.search_hypotheses(query, domain, limit=limit)
            elif type_name == "benchmark":
                items = self.sqlite.search_benchmarks(query, limit=limit)
            elif type_name == "claim":
                items = self.sqlite.search_claims(query, domain, limit=limit)
            else:
                continue

            for item in items:
                item["_type"] = type_name
                item["_strategy"] = "sqlite_fts5"
            results.extend(items)

        return results[:limit]

    def _get_types(self, mem_type: str) -> list:
        """Get list of types to search."""
        type_map = {
            None: ["paper", "hypothesis", "benchmark", "claim"],
            "paper": ["paper"],
            "hypothesis": ["hypothesis"],
            "benchmark": ["benchmark"],
            "claim": ["claim"],
        }
        return type_map.get(mem_type, ["paper", "hypothesis", "benchmark", "claim"])

    def _get_sqlite_ids(self, type_name: str, domain: str) -> list:
        """Get all relevant IDs from SQLite for a type.
        These IDs must match the format stored in ChromaDB."""
        if type_name == "paper":
            items = self.sqlite.search_papers("", domain, limit=1000)
            # paper_id already has 'paper_' prefix, use as-is
            return [item.get('paper_id', '') for item in items]
        elif type_name == "hypothesis":
            items = self.sqlite.search_hypotheses("", domain, limit=1000)
            return [item.get("hyp_id", "") for item in items]
        elif type_name == "benchmark":
            items = self.sqlite.search_benchmarks("", limit=1000)
            return [item.get("bench_id", "") for item in items]
        elif type_name == "claim":
            items = self.sqlite.search_claims("", domain, limit=1000)
            return [item.get("claim_id", "") for item in items]
        return []

    def _intersect_with_ranking(self, sqlite_ids: list,
                                chroma_doc_ids: list) -> list:
        """Intersect SQLite IDs with Chroma-ranked IDs, preserving rank order."""
        sqlite_set = set(sqlite_ids)
        ranked = []
        seen = set()

        for doc_id in chroma_doc_ids:
            if doc_id in sqlite_set and doc_id not in seen:
                ranked.append(doc_id)
                seen.add(doc_id)

        return ranked

    def _hydrate(self, type_name: str, ids: list) -> list:
        """Hydrate results from SQLite."""
        results = []
        for doc_id in ids:
            if type_name == "paper":
                items = self.sqlite.conn.execute(
                    "SELECT * FROM papers WHERE paper_id = ?", (doc_id,)
                ).fetchall()
                if items:
                    item = dict(items[0])
                    item["_type"] = "paper"
                    item["_strategy"] = "hybrid"
                    results.append(item)
            elif type_name == "hypothesis":
                items = self.sqlite.conn.execute(
                    "SELECT * FROM hypotheses WHERE hyp_id = ?", (doc_id,)
                ).fetchall()
                if items:
                    item = dict(items[0])
                    item["_type"] = "hypothesis"
                    item["_strategy"] = "hybrid"
                    results.append(item)
            elif type_name == "benchmark":
                items = self.sqlite.conn.execute(
                    "SELECT * FROM benchmarks WHERE bench_id = ?", (doc_id,)
                ).fetchall()
                if items:
                    item = dict(items[0])
                    item["_type"] = "benchmark"
                    item["_strategy"] = "hybrid"
                    results.append(item)
            elif type_name == "claim":
                items = self.sqlite.conn.execute(
                    "SELECT * FROM claims WHERE claim_id = ?", (doc_id,)
                ).fetchall()
                if items:
                    item = dict(items[0])
                    item["_type"] = "claim"
                    item["_strategy"] = "hybrid"
                    results.append(item)

        return results

    def get_stats(self) -> dict:
        """Get combined search engine statistics."""
        return {
            "sqlite": self.sqlite.get_stats(),
            "chroma": self.chroma.get_stats(),
            "strategy": "hybrid" if self.chroma.available else "sqlite_fts5"
        }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="ChromaDB Vector Search CLI")
    parser.add_argument("command", choices=["search", "stats", "index"])
    parser.add_argument("--query", "-q", help="Search query")
    parser.add_argument("--type", "-t", help="Memory type filter")
    parser.add_argument("--domain", "-d", help="Domain filter")
    parser.add_argument("--limit", "-l", type=int, default=10)
    args = parser.parse_args()

    engine = HybridSearchEngine()

    if args.command == "search":
        if not args.query:
            print("Error: --query required")
            import sys; sys.exit(1)
        results = engine.search(args.query, args.type, args.domain, args.limit)
        for r in results:
            strategy = r.pop("_strategy", "unknown")
            type_name = r.pop("_type", "unknown")
            preview = r.get("title", r.get("content", ""))[:100]
            print(f"[{type_name}] ({strategy}) {preview}")
        print(f"\nFound {len(results)} results")

    elif args.command == "stats":
        stats = engine.get_stats()
        print(json.dumps(stats, indent=2))

    elif args.command == "index":
        # Index all existing JSONL data into Chroma
        from migrate_jsonl_to_sqlite import migrate
        migrate()  # First ensure SQLite is up to date

        from sqlite_store import SQLiteKnowledgeStore
        sqlite = SQLiteKnowledgeStore()

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
        added = engine.chroma.add_documents_batch(docs)
        print(f"Indexed {added} papers")

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
        added = engine.chroma.add_documents_batch(docs)
        print(f"Indexed {added} hypotheses")

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
        added = engine.chroma.add_documents_batch(docs)
        print(f"Indexed {added} benchmarks")

        print(f"\nTotal documents in Chroma: {engine.chroma.count()}")

    sqlite.close()
