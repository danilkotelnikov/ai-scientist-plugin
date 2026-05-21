"""
SQLite Knowledge Store with FTS5 Full-Text Search

Adapted from claude-mem's database architecture:
- SQLite with WAL mode for concurrent reads
- FTS5 virtual tables for full-text search
- Structured queries with filters (type, date, project/domain)
- Progressive disclosure: index → details pattern

This replaces the JSONL-based storage with proper relational storage
while maintaining backward compatibility with existing JSONL data.
"""

import hashlib
import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


class SQLiteKnowledgeStore:
    """SQLite-backed knowledge store with FTS5 full-text search."""

    SCHEMA_VERSION = 1

    def __init__(self, base_dir: str = None, db_path: str = None):
        if base_dir is None:
            base_dir = os.path.expanduser("~/.ai-scientist")
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

        if db_path is None:
            db_path = str(self.base_dir / "knowledge.db")
        self.db_path = db_path

        self._conn = None
        self._init_db()

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode = WAL")
            self._conn.execute("PRAGMA foreign_keys = ON")
        return self._conn

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    def _init_db(self):
        """Initialize database schema."""
        c = self.conn
        c.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY
            )
        """)

        # Check if we need to run migrations
        row = c.execute("SELECT version FROM schema_version").fetchone()
        current_version = row[0] if row else 0

        if current_version < self.SCHEMA_VERSION:
            self._run_migrations(current_version)

    def _run_migrations(self, from_version: int):
        """Run schema migrations."""
        c = self.conn

        if from_version < 1:
            # Core tables (inspired by claude-mem's schema)
            c.executescript("""
                -- Papers table
                CREATE TABLE IF NOT EXISTS papers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    paper_id TEXT UNIQUE NOT NULL,
                    title TEXT NOT NULL,
                    authors TEXT,
                    year INTEGER,
                    doi TEXT,
                    journal TEXT,
                    url TEXT,
                    abstract TEXT,
                    source TEXT,
                    keywords TEXT,
                    domain TEXT,
                    source_job TEXT,
                    indexed_at TEXT NOT NULL,
                    created_at_epoch REAL NOT NULL
                );

                -- Hypotheses table
                CREATE TABLE IF NOT EXISTS hypotheses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    hyp_id TEXT UNIQUE NOT NULL,
                    content TEXT NOT NULL,
                    source_job TEXT NOT NULL,
                    keywords TEXT,
                    metadata TEXT,
                    domain TEXT,
                    experiment_exit_code INTEGER,
                    manuscript_words INTEGER,
                    papers_cited INTEGER,
                    self_review_score REAL,
                    created_at TEXT NOT NULL,
                    created_at_epoch REAL NOT NULL
                );

                -- Benchmarks table
                CREATE TABLE IF NOT EXISTS benchmarks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bench_id TEXT UNIQUE NOT NULL,
                    content TEXT NOT NULL,
                    source_job TEXT NOT NULL,
                    keywords TEXT,
                    metadata TEXT,
                    exit_code INTEGER,
                    fix_attempts INTEGER DEFAULT 0,
                    npy_files INTEGER DEFAULT 0,
                    figures_generated INTEGER DEFAULT 0,
                    runtime_seconds REAL,
                    created_at TEXT NOT NULL,
                    created_at_epoch REAL NOT NULL
                );

                -- Claims table
                CREATE TABLE IF NOT EXISTS claims (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    claim_id TEXT UNIQUE NOT NULL,
                    content TEXT NOT NULL,
                    source_job TEXT,
                    word_count INTEGER,
                    refs_count INTEGER,
                    domain TEXT,
                    created_at TEXT NOT NULL,
                    created_at_epoch REAL NOT NULL
                );

                -- Knowledge graph triples
                CREATE TABLE IF NOT EXISTS triples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    subject TEXT NOT NULL,
                    predicate TEXT NOT NULL,
                    object TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    created_at_epoch REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_triples_subject ON triples(subject);
                CREATE INDEX IF NOT EXISTS idx_triples_predicate ON triples(predicate);
                CREATE INDEX IF NOT EXISTS idx_triples_object ON triples(object);

                -- Trajectories table
                CREATE TABLE IF NOT EXISTS trajectories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    domain TEXT,
                    topic TEXT,
                    papers_found INTEGER,
                    word_count INTEGER,
                    exit_code INTEGER,
                    success INTEGER,
                    metadata TEXT,
                    created_at TEXT NOT NULL,
                    created_at_epoch REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_trajectories_job ON trajectories(job_id);
                CREATE INDEX IF NOT EXISTS idx_trajectories_phase ON trajectories(phase);

                -- FTS5 virtual tables for full-text search
                CREATE VIRTUAL TABLE IF NOT EXISTS papers_fts USING fts5(
                    title,
                    abstract,
                    authors,
                    keywords,
                    source,
                    content='papers',
                    content_rowid='id'
                );

                CREATE VIRTUAL TABLE IF NOT EXISTS hypotheses_fts USING fts5(
                    content,
                    keywords,
                    domain,
                    content='hypotheses',
                    content_rowid='id'
                );

                CREATE VIRTUAL TABLE IF NOT EXISTS benchmarks_fts USING fts5(
                    content,
                    keywords,
                    content='benchmarks',
                    content_rowid='id'
                );

                CREATE VIRTUAL TABLE IF NOT EXISTS claims_fts USING fts5(
                    content,
                    domain,
                    content='claims',
                    content_rowid='id'
                );

                -- Triggers to keep FTS tables in sync
                CREATE TRIGGER IF NOT EXISTS papers_ai AFTER INSERT ON papers BEGIN
                    INSERT INTO papers_fts(rowid, title, abstract, authors, keywords, source)
                    VALUES (new.id, new.title, new.abstract, new.authors, new.keywords, new.source);
                END;

                CREATE TRIGGER IF NOT EXISTS papers_ad AFTER DELETE ON papers BEGIN
                    INSERT INTO papers_fts(papers_fts, rowid, title, abstract, authors, keywords, source)
                    VALUES('delete', old.id, old.title, old.abstract, old.authors, old.keywords, old.source);
                END;

                CREATE TRIGGER IF NOT EXISTS papers_au AFTER UPDATE ON papers BEGIN
                    INSERT INTO papers_fts(papers_fts, rowid, title, abstract, authors, keywords, source)
                    VALUES('delete', old.id, old.title, old.abstract, old.authors, old.keywords, old.source);
                    INSERT INTO papers_fts(rowid, title, abstract, authors, keywords, source)
                    VALUES (new.id, new.title, new.abstract, new.authors, new.keywords, new.source);
                END;

                CREATE TRIGGER IF NOT EXISTS hypotheses_ai AFTER INSERT ON hypotheses BEGIN
                    INSERT INTO hypotheses_fts(rowid, content, keywords, domain)
                    VALUES (new.id, new.content, new.keywords, new.domain);
                END;

                CREATE TRIGGER IF NOT EXISTS hypotheses_ad AFTER DELETE ON hypotheses BEGIN
                    INSERT INTO hypotheses_fts(hypotheses_fts, rowid, content, keywords, domain)
                    VALUES('delete', old.id, old.content, old.keywords, old.domain);
                END;

                CREATE TRIGGER IF NOT EXISTS hypotheses_au AFTER UPDATE ON hypotheses BEGIN
                    INSERT INTO hypotheses_fts(hypotheses_fts, rowid, content, keywords, domain)
                    VALUES('delete', old.id, old.content, old.keywords, old.domain);
                    INSERT INTO hypotheses_fts(rowid, content, keywords, domain)
                    VALUES (new.id, new.content, new.keywords, new.domain);
                END;

                CREATE TRIGGER IF NOT EXISTS benchmarks_ai AFTER INSERT ON benchmarks BEGIN
                    INSERT INTO benchmarks_fts(rowid, content, keywords)
                    VALUES (new.id, new.content, new.keywords);
                END;

                CREATE TRIGGER IF NOT EXISTS benchmarks_ad AFTER DELETE ON benchmarks BEGIN
                    INSERT INTO benchmarks_fts(benchmarks_fts, rowid, content, keywords)
                    VALUES('delete', old.id, old.content, old.keywords);
                END;

                CREATE TRIGGER IF NOT EXISTS claims_ai AFTER INSERT ON claims BEGIN
                    INSERT INTO claims_fts(rowid, content, domain)
                    VALUES (new.id, new.content, new.domain);
                END;

                CREATE TRIGGER IF NOT EXISTS claims_ad AFTER DELETE ON claims BEGIN
                    INSERT INTO claims_fts(claims_fts, rowid, content, domain)
                    VALUES('delete', old.id, old.content, old.domain);
                END;
            """)

            # Rebuild FTS tables from existing data (in case of migration from JSONL)
            self._rebuild_fts()

            c.execute("INSERT OR REPLACE INTO schema_version (version) VALUES (?)", (1,))
            c.commit()

    def _rebuild_fts(self):
        """Rebuild FTS tables from base tables."""
        c = self.conn
        try:
            c.execute("DELETE FROM papers_fts")
            c.execute("""
                INSERT INTO papers_fts(rowid, title, abstract, authors, keywords, source)
                SELECT id, title, abstract, authors, keywords, source FROM papers
            """)
        except sqlite3.OperationalError:
            pass  # FTS table may not exist yet

        try:
            c.execute("DELETE FROM hypotheses_fts")
            c.execute("""
                INSERT INTO hypotheses_fts(rowid, content, keywords, domain)
                SELECT id, content, keywords, domain FROM hypotheses
            """)
        except sqlite3.OperationalError:
            pass

        try:
            c.execute("DELETE FROM benchmarks_fts")
            c.execute("""
                INSERT INTO benchmarks_fts(rowid, content, keywords)
                SELECT id, content, keywords FROM benchmarks
            """)
        except sqlite3.OperationalError:
            pass

        try:
            c.execute("DELETE FROM claims_fts")
            c.execute("""
                INSERT INTO claims_fts(rowid, content, domain)
                SELECT id, content, domain FROM claims
            """)
        except sqlite3.OperationalError:
            pass

        c.commit()

    # --- Paper operations ---

    def add_paper(self, paper: dict, domain: str = None, source_job: str = None) -> str:
        """Add a paper. Returns paper_id. Deduplicates by DOI or title."""
        doi = (paper.get("doi") or "").lower().strip()
        title = paper.get("title") or ""

        # Check for duplicates
        if doi:
            existing = self.conn.execute(
                "SELECT paper_id FROM papers WHERE doi = ?", (doi,)
            ).fetchone()
            if existing:
                return existing[0]

        if title:
            existing = self.conn.execute(
                "SELECT paper_id FROM papers WHERE title = ?", (title,)
            ).fetchone()
            if existing:
                return existing[0]

        paper_id = "paper_" + hashlib.md5(
            f"{title}{doi}".encode()
        ).hexdigest()[:12]

        now = time.time()
        now_iso = datetime.now(timezone.utc).isoformat()

        self.conn.execute("""
            INSERT OR IGNORE INTO papers (
                paper_id, title, authors, year, doi, journal, url,
                abstract, source, keywords, domain, source_job,
                indexed_at, created_at_epoch
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            paper_id,
            title,
            json.dumps(paper.get("authors", [])),
            paper.get("year"),
            doi or None,
            paper.get("journal"),
            paper.get("url"),
            paper.get("abstract", "")[:2000],
            paper.get("source"),
            json.dumps(self._extract_keywords(f"{title} {paper.get('abstract', '')}")),
            domain,
            source_job,
            now_iso,
            now
        ))
        self.conn.commit()
        return paper_id

    def add_papers_batch(self, papers: list, domain: str = None, source_job: str = None) -> int:
        """Add multiple papers at once. Returns count added."""
        count = 0
        for paper in papers:
            pid = self.add_paper(paper, domain, source_job)
            if not pid.startswith("paper_") or len(pid) > 5:  # Not a duplicate
                count += 1
        return count

    def search_papers(self, query: str, domain: str = None,
                      year_min: int = None, limit: int = 20) -> list:
        """Search papers using FTS5 full-text search."""
        if not query:
            # Filter-only query
            sql = "SELECT * FROM papers WHERE 1=1"
            params = []
            if domain:
                sql += " AND domain = ?"
                params.append(domain)
            if year_min:
                sql += " AND year >= ?"
                params.append(year_min)
            sql += " ORDER BY created_at_epoch DESC LIMIT ?"
            params.append(limit)
            rows = self.conn.execute(sql, params).fetchall()
        else:
            # FTS5 search
            fts_query = " OR ".join(query.split())
            sql = """
                SELECT p.* FROM papers p
                JOIN papers_fts f ON p.id = f.rowid
                WHERE papers_fts MATCH ?
            """
            params = [fts_query]
            if domain:
                sql += " AND p.domain = ?"
                params.append(domain)
            if year_min:
                sql += " AND p.year >= ?"
                params.append(year_min)
            sql += " ORDER BY rank LIMIT ?"
            params.append(limit)
            rows = self.conn.execute(sql, params).fetchall()

        return [dict(r) for r in rows]

    def get_papers_by_ids(self, ids: list) -> list:
        """Get papers by their database IDs (for progressive disclosure hydration)."""
        if not ids:
            return []
        placeholders = ",".join("?" * len(ids))
        rows = self.conn.execute(
            f"SELECT * FROM papers WHERE id IN ({placeholders})", ids
        ).fetchall()
        return [dict(r) for r in rows]

    # --- Hypothesis operations ---

    def add_hypothesis(self, job_id: str, content: str, domain: str,
                       metadata: dict = None) -> str:
        """Add a hypothesis with outcome tracking."""
        hyp_id = "hypothesis_" + hashlib.md5(
            f"{job_id}{content[:50]}".encode()
        ).hexdigest()[:12]

        now = time.time()
        now_iso = datetime.now(timezone.utc).isoformat()
        meta = metadata or {}

        self.conn.execute("""
            INSERT OR IGNORE INTO hypotheses (
                hyp_id, content, source_job, keywords, metadata, domain,
                experiment_exit_code, manuscript_words, papers_cited,
                self_review_score, created_at, created_at_epoch
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            hyp_id,
            content[:10000],
            job_id,
            json.dumps(self._extract_keywords(content)),
            json.dumps(meta),
            domain,
            meta.get("experiment_exit_code"),
            meta.get("manuscript_words"),
            meta.get("papers_cited"),
            meta.get("self_review_score"),
            now_iso,
            now
        ))
        self.conn.commit()
        return hyp_id

    def search_hypotheses(self, query: str, domain: str = None,
                          exit_code: int = None, limit: int = 10) -> list:
        """Search hypotheses using FTS5."""
        if not query:
            sql = "SELECT * FROM hypotheses WHERE 1=1"
            params = []
            if domain:
                sql += " AND domain = ?"
                params.append(domain)
            if exit_code is not None:
                sql += " AND experiment_exit_code = ?"
                params.append(exit_code)
            sql += " ORDER BY created_at_epoch DESC LIMIT ?"
            params.append(limit)
            rows = self.conn.execute(sql, params).fetchall()
        else:
            fts_query = " OR ".join(query.split())
            sql = """
                SELECT h.* FROM hypotheses h
                JOIN hypotheses_fts f ON h.id = f.rowid
                WHERE hypotheses_fts MATCH ?
            """
            params = [fts_query]
            if domain:
                sql += " AND h.domain = ?"
                params.append(domain)
            if exit_code is not None:
                sql += " AND h.experiment_exit_code = ?"
                params.append(exit_code)
            sql += " ORDER BY rank LIMIT ?"
            params.append(limit)
            rows = self.conn.execute(sql, params).fetchall()

        return [dict(r) for r in rows]

    # --- Benchmark operations ---

    def add_benchmark(self, job_id: str, content: str, metadata: dict) -> str:
        """Add a benchmark result."""
        bench_id = "benchmark_" + hashlib.md5(
            f"{job_id}{datetime.now().isoformat()}".encode()
        ).hexdigest()[:12]

        now = time.time()
        now_iso = datetime.now(timezone.utc).isoformat()

        self.conn.execute("""
            INSERT OR IGNORE INTO benchmarks (
                bench_id, content, source_job, keywords, metadata,
                exit_code, fix_attempts, npy_files, figures_generated,
                runtime_seconds, created_at, created_at_epoch
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            bench_id,
            content[:2000],
            job_id,
            json.dumps(self._extract_keywords(content)),
            json.dumps(metadata),
            metadata.get("exit_code", -1),
            metadata.get("fix_attempts", 0),
            metadata.get("npy_files", 0),
            metadata.get("figures_generated", 0),
            metadata.get("runtime_seconds"),
            now_iso,
            now
        ))
        self.conn.commit()
        return bench_id

    def search_benchmarks(self, query: str, exit_code: int = None,
                          limit: int = 10) -> list:
        """Search benchmarks using FTS5."""
        if not query:
            sql = "SELECT * FROM benchmarks WHERE 1=1"
            params = []
            if exit_code is not None:
                sql += " AND exit_code = ?"
                params.append(exit_code)
            sql += " ORDER BY created_at_epoch DESC LIMIT ?"
            params.append(limit)
            rows = self.conn.execute(sql, params).fetchall()
        else:
            fts_query = " OR ".join(query.split())
            sql = """
                SELECT b.* FROM benchmarks b
                JOIN benchmarks_fts f ON b.id = f.rowid
                WHERE benchmarks_fts MATCH ?
            """
            params = [fts_query]
            if exit_code is not None:
                sql += " AND b.exit_code = ?"
                params.append(exit_code)
            sql += " ORDER BY rank LIMIT ?"
            params.append(limit)
            rows = self.conn.execute(sql, params).fetchall()

        return [dict(r) for r in rows]

    # --- Claim operations ---

    def add_claim(self, job_id: str, content: str, domain: str = None,
                  word_count: int = None, refs_count: int = None) -> str:
        """Add a manuscript claim."""
        claim_id = "claim_" + hashlib.md5(
            f"{job_id}{content[:50]}".encode()
        ).hexdigest()[:12]

        now = time.time()
        now_iso = datetime.now(timezone.utc).isoformat()

        self.conn.execute("""
            INSERT OR IGNORE INTO claims (
                claim_id, content, source_job, word_count, refs_count,
                domain, created_at, created_at_epoch
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            claim_id,
            content[:5000],
            job_id,
            word_count,
            refs_count,
            domain,
            now_iso,
            now
        ))
        self.conn.commit()
        return claim_id

    def search_claims(self, query: str, domain: str = None, limit: int = 10) -> list:
        """Search claims using FTS5."""
        if not query:
            sql = "SELECT * FROM claims WHERE 1=1"
            params = []
            if domain:
                sql += " AND domain = ?"
                params.append(domain)
            sql += " ORDER BY created_at_epoch DESC LIMIT ?"
            params.append(limit)
            rows = self.conn.execute(sql, params).fetchall()
        else:
            fts_query = " OR ".join(query.split())
            sql = """
                SELECT c.* FROM claims c
                JOIN claims_fts f ON c.id = f.rowid
                WHERE claims_fts MATCH ?
            """
            params = [fts_query]
            if domain:
                sql += " AND c.domain = ?"
                params.append(domain)
            sql += " ORDER BY rank LIMIT ?"
            params.append(limit)
            rows = self.conn.execute(sql, params).fetchall()

        return [dict(r) for r in rows]

    # --- Triple operations ---

    def add_triple(self, subject: str, predicate: str, object_: str):
        """Add a knowledge graph triple."""
        now = time.time()
        now_iso = datetime.now(timezone.utc).isoformat()

        self.conn.execute("""
            INSERT INTO triples (subject, predicate, object, timestamp, created_at_epoch)
            VALUES (?, ?, ?, ?, ?)
        """, (subject, predicate, object_, now_iso, now))
        self.conn.commit()

    def query_triples(self, subject: str = None, predicate: str = None,
                      object_: str = None) -> list:
        """Query knowledge graph triples."""
        sql = "SELECT * FROM triples WHERE 1=1"
        params = []
        if subject:
            sql += " AND subject = ?"
            params.append(subject)
        if predicate:
            sql += " AND predicate = ?"
            params.append(predicate)
        if object_:
            sql += " AND object = ?"
            params.append(object_)
        sql += " ORDER BY created_at_epoch DESC"
        rows = self.conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    # --- Trajectory operations ---

    def add_trajectory(self, entry: dict):
        """Add a trajectory log entry."""
        now = time.time()
        now_iso = datetime.now(timezone.utc).isoformat()

        self.conn.execute("""
            INSERT INTO trajectories (
                job_id, phase, domain, topic, papers_found, word_count,
                exit_code, success, metadata, created_at, created_at_epoch
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            entry.get("job_id", ""),
            entry.get("phase", ""),
            entry.get("domain"),
            entry.get("topic"),
            entry.get("papers_found"),
            entry.get("word_count"),
            entry.get("exit_code"),
            1 if entry.get("success") else 0,
            json.dumps({k: v for k, v in entry.items()
                        if k not in ("job_id", "phase", "domain", "topic",
                                     "papers_found", "word_count", "exit_code", "success")}),
            now_iso,
            now
        ))
        self.conn.commit()

    def get_trajectories_by_job(self, job_id: str) -> list:
        """Get all trajectories for a specific job."""
        rows = self.conn.execute(
            "SELECT * FROM trajectories WHERE job_id = ? ORDER BY created_at_epoch",
            (job_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    # --- Stats ---

    def get_stats(self) -> dict:
        """Get knowledge store statistics."""
        stats = {}
        for table in ["papers", "hypotheses", "benchmarks", "claims", "triples", "trajectories"]:
            row = self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            stats[table] = row[0]
        return stats

    # --- Progressive disclosure (claude-mem pattern) ---

    def search_index(self, query: str, mem_type: str = None,
                     domain: str = None, limit: int = 20) -> list:
        """
        Layer 1: Get compact index with IDs (~50-100 tokens/result).
        This is the first step in the progressive disclosure workflow.
        """
        results = []

        if mem_type is None or mem_type == "paper":
            papers = self.search_papers(query, domain, limit=limit)
            for p in papers:
                results.append({
                    "type": "paper",
                    "id": p["id"],
                    "title": p.get("title", "")[:80],
                    "year": p.get("year"),
                    "source": p.get("source"),
                    "domain": p.get("domain"),
                    "token_estimate": 50
                })

        if mem_type is None or mem_type == "hypothesis":
            hyps = self.search_hypotheses(query, domain, limit=limit)
            for h in hyps:
                results.append({
                    "type": "hypothesis",
                    "id": h["id"],
                    "preview": h.get("content", "")[:100],
                    "domain": h.get("domain"),
                    "exit_code": h.get("experiment_exit_code"),
                    "token_estimate": 60
                })

        if mem_type is None or mem_type == "benchmark":
            benches = self.search_benchmarks(query, limit=limit)
            for b in benches:
                results.append({
                    "type": "benchmark",
                    "id": b["id"],
                    "preview": b.get("content", "")[:80],
                    "exit_code": b.get("exit_code"),
                    "token_estimate": 50
                })

        if mem_type is None or mem_type == "claim":
            claims = self.search_claims(query, domain, limit=limit)
            for c in claims:
                results.append({
                    "type": "claim",
                    "id": c["id"],
                    "preview": c.get("content", "")[:80],
                    "domain": c.get("domain"),
                    "token_estimate": 50
                })

        return results[:limit]

    def get_details(self, ids: list, mem_type: str = None) -> list:
        """
        Layer 3: Fetch full details ONLY for filtered IDs (~500-1000 tokens/result).
        This is the final step in the progressive disclosure workflow.
        """
        details = []

        if mem_type is None or mem_type == "paper":
            paper_ids = [i for i in ids if isinstance(i, int)]
            if paper_ids:
                papers = self.get_papers_by_ids(paper_ids)
                details.extend([{"type": "paper", **p} for p in papers])

        if mem_type is None or mem_type == "hypothesis":
            if ids:
                placeholders = ",".join("?" * len(ids))
                rows = self.conn.execute(
                    f"SELECT * FROM hypotheses WHERE id IN ({placeholders})", ids
                ).fetchall()
                details.extend([{"type": "hypothesis", **dict(r)} for r in rows])

        if mem_type is None or mem_type == "benchmark":
            if ids:
                placeholders = ",".join("?" * len(ids))
                rows = self.conn.execute(
                    f"SELECT * FROM benchmarks WHERE id IN ({placeholders})", ids
                ).fetchall()
                details.extend([{"type": "benchmark", **dict(r)} for r in rows])

        if mem_type is None or mem_type == "claim":
            if ids:
                placeholders = ",".join("?" * len(ids))
                rows = self.conn.execute(
                    f"SELECT * FROM claims WHERE id IN ({placeholders})", ids
                ).fetchall()
                details.extend([{"type": "claim", **dict(r)} for r in rows])

        return details

    # --- Utility ---

    def _extract_keywords(self, text: str, max_keywords: int = 15) -> str:
        """Extract top keywords from text. Returns JSON string for storage."""
        import re
        from collections import Counter
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
        tokens = [t for t in tokens if t not in stop_words and len(t) > 2]
        if not tokens:
            return "[]"
        counter = Counter(tokens)
        return json.dumps([word for word, _ in counter.most_common(max_keywords)])


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="SQLite Knowledge Store CLI")
    parser.add_argument("command", choices=["stats", "search", "query", "migrate"])
    parser.add_argument("--query", "-q", help="Search query")
    parser.add_argument("--type", "-t", help="Memory type filter")
    parser.add_argument("--domain", "-d", help="Domain filter")
    parser.add_argument("--limit", "-l", type=int, default=10)
    parser.add_argument("--subject", help="Triple subject")
    parser.add_argument("--predicate", help="Triple predicate")
    parser.add_argument("--object", help="Triple object")
    args = parser.parse_args()

    store = SQLiteKnowledgeStore()

    if args.command == "stats":
        stats = store.get_stats()
        print(json.dumps(stats, indent=2))

    elif args.command == "search":
        if not args.query:
            print("Error: --query required for search")
            import sys; sys.exit(1)
        results = store.search_index(args.query, args.type, args.domain, args.limit)
        for r in results:
            preview = r.get("title", r.get("preview", ""))
            print(f"[{r['type']}] (id={r['id']}) {preview}")
        print(f"\nFound {len(results)} results")

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
