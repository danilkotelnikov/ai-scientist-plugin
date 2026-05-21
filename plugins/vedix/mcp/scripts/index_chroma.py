"""Index existing SQLite data into ChromaDB for semantic search."""
import sys
import json
sys.path.insert(0, 'lib')

from sqlite_store import SQLiteKnowledgeStore
from chroma_store import ChromaVectorStore

sqlite = SQLiteKnowledgeStore()
chroma = ChromaVectorStore()

print(f"ChromaDB available: {chroma.available}")

if not chroma.available:
    print("ChromaDB not available. Install with: pip install chromadb")
    sys.exit(1)

# Index papers
papers = sqlite.conn.execute("SELECT * FROM papers").fetchall()
docs = []
for p in papers:
    p = dict(p)
    paper_id = p.get('paper_id', '')
    # paper_id already has 'paper_' prefix
    docs.append({
        "id": paper_id,
        "text": f"{p.get('title', '')} {p.get('abstract', '')}",
        "metadata": {
            "doc_type": "paper",
            "domain": p.get("domain", ""),
            "source_job": p.get("source_job", ""),
            "created_at": p.get("indexed_at", ""),
        }
    })
added = chroma.add_documents_batch(docs)
print(f"Indexed {added} papers into ChromaDB")

# Index hypotheses
hyps = sqlite.conn.execute("SELECT * FROM hypotheses").fetchall()
docs = []
for h in hyps:
    h = dict(h)
    hyp_id = h.get('hyp_id', '')
    docs.append({
        "id": hyp_id,
        "text": h.get("content", ""),
        "metadata": {
            "doc_type": "hypothesis",
            "domain": h.get("domain", ""),
            "source_job": h.get("source_job", ""),
            "created_at": h.get("created_at", ""),
        }
    })
added = chroma.add_documents_batch(docs)
print(f"Indexed {added} hypotheses into ChromaDB")

# Index benchmarks
benches = sqlite.conn.execute("SELECT * FROM benchmarks").fetchall()
docs = []
for b in benches:
    b = dict(b)
    bench_id = b.get('bench_id', '')
    docs.append({
        "id": bench_id,
        "text": b.get("content", ""),
        "metadata": {
            "doc_type": "benchmark",
            "source_job": b.get("source_job", ""),
            "created_at": b.get("created_at", ""),
        }
    })
added = chroma.add_documents_batch(docs)
print(f"Indexed {added} benchmarks into ChromaDB")

print(f"\nTotal ChromaDB documents: {chroma.count()}")

# Test semantic search
print("\n--- Semantic Search Test ---")
results = chroma.search("protein folding", limit=3, doc_type="paper")
print(f"Semantic search for 'protein folding': {len(results)} results")
for r in results:
    print(f"  [{r['doc_type']}] score={r['score']:.3f} doc_id={r['doc_id'][:40]}")

sqlite.close()
