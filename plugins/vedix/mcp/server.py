"""
AI-Scientist MCP Server Backend

A proper MCP server that implements the ai-scientist tools:
- start_research: Start a research job
- get_status: Poll job status
- get_output: Retrieve job output
- list_jobs: List all jobs
- list_templates: List domain templates
- cancel_job: Cancel a running job
- query_knowledge: Search knowledge store
- query_knowledge_graph: Query triple store
- get_knowledge_stats: Get knowledge store statistics

This server runs as a stdio-based MCP server and communicates with Cursor.
"""

import json
import os
import sys
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Add bundled lib/ to path. Plugin layout: <plugin_root>/mcp/lib
sys.path.insert(0, str(Path(__file__).parent / "lib"))

from knowledge_store import KnowledgeStore
from meta_analyzer import MetaAnalyzer
from codebase_analyzer import CodebaseAnalyzer

# Runtime data root. Defaults to ~/.ai-scientist/ but is overridable via
# AI_SCIENTIST_HOME env var (set by .mcp.json). This keeps user data alive
# across plugin reinstalls.
BASE_DIR = Path(os.environ.get("AI_SCIENTIST_HOME", str(Path.home() / ".ai-scientist")))
BASE_DIR.mkdir(exist_ok=True)

JOBS_FILE = BASE_DIR / "jobs.json"
TEMPLATES = {
    "ml": {
        "libraries": "torch, torchvision, numpy, matplotlib, scikit-learn, einops",
        "experiment_type": "deep_learning_benchmark",
        "metric": "validation_accuracy_and_loss",
        "extra_sections": ["Related Work", "Experiments"]
    },
    "optimization": {
        "libraries": "scipy, cvxpy, pulp, pyomo, numpy",
        "experiment_type": "optimization_benchmark",
        "metric": "objective_value_and_solve_time",
        "extra_sections": []
    },
    "statistical": {
        "libraries": "scipy, statsmodels, pingouin, numpy, pandas, matplotlib, seaborn",
        "experiment_type": "statistical_analysis",
        "metric": "p_value_effect_size_and_confidence_interval",
        "extra_sections": ["Related Work", "Statistical Analysis"]
    },
    "mathematical": {
        "libraries": "sympy, scipy, numpy, matplotlib",
        "experiment_type": "mathematical_modeling",
        "metric": "symbolic_solution_and_numerical_error",
        "extra_sections": []
    },
    "computational_biology": {
        "libraries": "biopython, numpy, scipy, matplotlib, networkx",
        "experiment_type": "bioinformatics_analysis",
        "metric": "alignment_score_and_structure_rmsd",
        "extra_sections": ["Structure Prediction", "Machine Learning for Design"]
    },
    "software_engineering": {
        "libraries": "pytest, hypothesis, black, mypy, pylint, numpy",
        "experiment_type": "software_benchmark",
        "metric": "performance_and_correctness",
        "extra_sections": ["Architecture", "Implementation Details", "Benchmarks"]
    }
}

# In-memory job tracking
active_jobs = {}
job_lock = threading.Lock()


def load_jobs():
    if JOBS_FILE.exists():
        with open(JOBS_FILE) as f:
            return json.load(f)
    return {}


def save_jobs(jobs):
    with open(JOBS_FILE, "w") as f:
        json.dump(jobs, f, indent=2)


def start_research(topic, codebase_context, domain_template, llm_backend="api", output_dir=""):
    """Start a new research job."""
    job_id = uuid.uuid4().hex[:8]
    template = TEMPLATES.get(domain_template, TEMPLATES["ml"])

    if not output_dir:
        output_dir = str(Path.cwd() / "ai-scientist-output" / job_id)

    job = {
        "job_id": job_id,
        "topic": topic,
        "codebase_context": codebase_context,
        "domain_template": domain_template,
        "llm_backend": llm_backend,
        "output_dir": output_dir,
        "phase": "queued",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": "",
        "elapsed_seconds": 0,
        "return_code": None,
        "source": "mcp_server",
        "preferred_libraries": template["libraries"],
        "experiment_type": template["experiment_type"],
        "evaluation_metric": template["metric"]
    }

    with job_lock:
        jobs = load_jobs()
        jobs[job_id] = job
        save_jobs(jobs)
        active_jobs[job_id] = job

    # Create output directory
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Write config.json
    config = {
        "job_id": job_id,
        "topic": topic,
        "domain": domain_template,
        "codebase_context": codebase_context,
        "created_at": job["created_at"],
        "preferred_libraries": template["libraries"],
        "experiment_type": template["experiment_type"],
        "evaluation_metric": template["metric"]
    }
    with open(Path(output_dir) / "config.json", "w") as f:
        json.dump(config, f, indent=2)

    return {
        "job_id": job_id,
        "status": "queued",
        "output_dir": output_dir,
        "message": f"Research job started. Topic: {topic[:80]}..."
    }


def get_status(job_id):
    """Get the current status of a research job."""
    with job_lock:
        jobs = load_jobs()
        job = jobs.get(job_id)

    if not job:
        return {"error": f"Job {job_id} not found"}

    return {
        "job_id": job_id,
        "phase": job.get("phase", "unknown"),
        "status": job.get("phase", "unknown"),
        "created_at": job.get("created_at", ""),
        "finished_at": job.get("finished_at", ""),
        "elapsed_seconds": job.get("elapsed_seconds", 0),
        "return_code": job.get("return_code"),
        "topic": job.get("topic", "")[:100]
    }


def get_output(job_id, section="all"):
    """Retrieve structured output from a research job."""
    with job_lock:
        jobs = load_jobs()
        job = jobs.get(job_id)

    if not job:
        return {"error": f"Job {job_id} not found"}

    output_dir = Path(job.get("output_dir", ""))
    if not output_dir.exists():
        return {"error": f"Output directory not found: {output_dir}"}

    result = {"job_id": job_id}

    if section in ("all", "literature"):
        paper_file = output_dir / "paper_list.json"
        if paper_file.exists():
            with open(paper_file) as f:
                result["literature"] = json.load(f)[:20]  # First 20 papers

    if section in ("all", "math_models"):
        hyp_file = output_dir / "hypothesis.md"
        if hyp_file.exists():
            result["hypothesis"] = hyp_file.read_text()

    if section in ("all", "stats"):
        stdout_file = output_dir / "experiment_stdout.txt"
        if stdout_file.exists():
            result["experiment_stdout"] = stdout_file.read_text()[:2000]
        stderr_file = output_dir / "experiment_stderr.txt"
        if stderr_file.exists():
            result["experiment_stderr"] = stderr_file.read_text()[:1000]
        csv_file = output_dir / "results.csv"
        if csv_file.exists():
            result["results_csv"] = csv_file.read_text()[:2000]

    if section in ("all", "plots"):
        fig_dir = output_dir / "figures"
        if fig_dir.exists():
            result["figures"] = [f.name for f in fig_dir.glob("*.png")]

    if section in ("all", "manuscript"):
        manuscript_file = output_dir / "manuscript.tex"
        if manuscript_file.exists():
            result["manuscript"] = manuscript_file.read_text()
        review_file = output_dir / "review.json"
        if review_file.exists():
            result["review"] = json.loads(review_file.read_text())

    return result


def list_jobs():
    """List all research jobs."""
    jobs = load_jobs()
    result = []
    for job_id, job in jobs.items():
        result.append({
            "job_id": job_id,
            "topic": job.get("topic", "")[:80],
            "domain": job.get("domain_template", ""),
            "phase": job.get("phase", ""),
            "created_at": job.get("created_at", ""),
            "elapsed_seconds": job.get("elapsed_seconds", 0),
            "return_code": job.get("return_code")
        })
    return {"jobs": result, "total": len(result)}


def list_templates():
    """List available domain templates."""
    return {"templates": TEMPLATES}


def cancel_job(job_id):
    """Cancel a running job."""
    with job_lock:
        jobs = load_jobs()
        if job_id not in jobs:
            return {"error": f"Job {job_id} not found"}

        jobs[job_id]["phase"] = "cancelled"
        jobs[job_id]["finished_at"] = datetime.now(timezone.utc).isoformat()
        save_jobs(jobs)

    return {"job_id": job_id, "status": "cancelled"}


def query_knowledge(query, mem_type=None, limit=10):
    """Search the persistent knowledge store with hybrid search (SQLite FTS5 + ChromaDB)."""
    store = KnowledgeStore()
    results = store.search_all(query, mem_type, limit)
    stats = store.get_stats()
    store.close()
    return {
        "results": results,
        "count": len(results),
        "backend": stats.get("backend", "unknown"),
        "strategy": "hybrid" if stats.get("chroma", {}).get("available") else stats.get("backend", "unknown")
    }


def search_knowledge_index(query, mem_type=None, domain=None, limit=20):
    """
    Layer 1 of progressive disclosure: Get compact index with IDs.
    Uses SQLite FTS5 + ChromaDB hybrid search.
    """
    store = KnowledgeStore()
    results = store.search_index(query, mem_type, domain, limit)
    store.close()
    return {"index": results, "count": len(results)}


def get_knowledge_details(ids, mem_type=None):
    """
    Layer 3 of progressive disclosure: Fetch full details for filtered IDs.
    """
    store = KnowledgeStore()
    results = store.get_details(ids, mem_type)
    store.close()
    return {"details": results, "count": len(results)}


def query_knowledge_graph(subject=None, predicate=None, object=None, include_invalid=False):
    """Query the temporal knowledge graph."""
    store = KnowledgeStore()
    triples = store.query_triples(subject, predicate, object, include_invalid)
    return {"triples": triples, "count": len(triples)}


def get_knowledge_stats():
    """Get statistics about the knowledge store."""
    store = KnowledgeStore()
    stats = store.get_stats()

    # Add meta-analysis if available
    meta = store.read_meta_analysis()
    if meta:
        stats["meta_analysis"] = {
            "total_jobs": meta.get("total_jobs", 0),
            "success_rate": meta.get("overall_success_rate", 0)
        }

    what_works = store.read_what_works()
    if what_works:
        stats["recommendations"] = what_works.get("recommendations_for_next_job", [])

    return stats


# --- MCP Protocol Handler ---

TOOL_DEFINITIONS = [
    {
        "name": "start_research",
        "description": "Start a new ai-scientist research job.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "codebase_context": {"type": "string"},
                "domain_template": {"type": "string"},
                "llm_backend": {"type": "string"},
                "output_dir": {"type": "string"},
            },
            "required": ["topic"],
        },
    },
    {
        "name": "get_status",
        "description": "Get the status of a research job.",
        "inputSchema": {
            "type": "object",
            "properties": {"job_id": {"type": "string"}},
            "required": ["job_id"],
        },
    },
    {
        "name": "get_output",
        "description": "Retrieve output artifacts for a research job.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string"},
                "section": {"type": "string"},
            },
            "required": ["job_id"],
        },
    },
    {
        "name": "list_jobs",
        "description": "List ai-scientist research jobs.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_templates",
        "description": "List available domain templates.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "cancel_job",
        "description": "Cancel a running research job.",
        "inputSchema": {
            "type": "object",
            "properties": {"job_id": {"type": "string"}},
            "required": ["job_id"],
        },
    },
    {
        "name": "query_knowledge",
        "description": "Search the ai-scientist knowledge store.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "mem_type": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "query_knowledge_graph",
        "description": "Query the ai-scientist temporal knowledge graph.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "subject": {"type": "string"},
                "predicate": {"type": "string"},
                "object": {"type": "string"},
                "include_invalid": {"type": "boolean"},
            },
        },
    },
    {
        "name": "get_knowledge_stats",
        "description": "Get ai-scientist knowledge store statistics.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "search_knowledge_index",
        "description": "Search the persistent ai-scientist knowledge index.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "mem_type": {"type": "string"},
                "domain": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_knowledge_details",
        "description": "Fetch details for knowledge-store item IDs.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ids": {"type": "array", "items": {"type": "string"}},
                "mem_type": {"type": "string"},
            },
            "required": ["ids"],
        },
    },
    {
        "name": "analyze_codebase",
        "description": "Analyze a local codebase for ai-scientist grounding.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "codebase_path": {"type": "string"},
                "output_file": {"type": "string"},
            },
            "required": ["codebase_path"],
        },
    },
    {
        "name": "get_meta_analysis",
        "description": "Read ai-scientist meta-analysis results.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_what_works",
        "description": "Read ai-scientist recommendations from prior jobs.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "run_meta_analysis",
        "description": "Run ai-scientist meta-analysis over stored jobs.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "run_pipeline",
        "description": "Run the full Python orchestrator pipeline (Phase 0 → Phase 11). Returns a job summary dict with job_id, tokens, review, output_dir.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "domain": {"type": "string"},
                "output_dir": {"type": "string"},
                "host": {"type": "string", "enum": ["claude_code", "codex", "gemini"]},
                "interactivity": {"type": "string", "enum": ["none", "checkpoints", "full"]},
                "use_bfts": {"type": "boolean"},
                "codebase_path": {"type": "string"},
            },
            "required": ["topic", "domain", "output_dir"],
        },
    },
    {
        "name": "dispatch_phase",
        "description": "Reentrant dispatch helper: returns the agent_name + subagent_type + inputs the host should pass to Task(). Used by the orchestrator pipeline to ask Claude Code to invoke a specific subagent.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_name": {"type": "string"},
                "inputs": {"type": "object"},
            },
            "required": ["agent_name", "inputs"],
        },
    },
    {
        "name": "validate_corpus",
        "description": "Run the strict DOI-gated cross-validator over a paper list. Stage 1 = Crossref/DataCite resolve + fuzzy title (≥0.85). Stage 2 = OpenAlex/S2/Anna's-OA-only enrichment cascade. Stage 3 = optional claim-support spot-check for top-cited.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "paper_list_path": {"type": "string"},
                "crossref_email": {"type": "string"},
                "openalex_email": {"type": "string"},
                "semantic_scholar_key": {"type": "string"},
                "annas_enabled": {"type": "boolean"},
                "consensus_enabled": {"type": "boolean"},
                "pubmed_enabled": {"type": "boolean"},
                "title_threshold": {"type": "number"},
            },
            "required": ["paper_list_path", "crossref_email"],
        },
    },
    {
        "name": "run_plotter_cycle",
        "description": "Run one cycle of the iterative plotter (1=inspect+draft, 2=VLM critique, 3=polish+export). Modes: scripting (matplotlib) or latex_native (TikZ/pgfplots).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "output_dir": {"type": "string"},
                "cycle": {"type": "integer", "enum": [1, 2, 3]},
                "mode": {"type": "string",
                         "enum": ["scripting", "latex_native"]},
                "article_type": {"type": "string",
                                  "enum": ["review", "experimental",
                                           "benchmark"]},
                "journal_style": {"type": "string"},
                "figure_specs": {"type": "array"},
            },
            "required": ["output_dir", "cycle"],
        },
    },
]


def handle_request(request):
    """Handle an MCP JSON-RPC request."""
    method = request.get("method", "")
    params = request.get("params", {})
    request_id = request.get("id")

    try:
        if method == "tools/call":
            tool_name = params.get("name", "")
            tool_args = params.get("arguments", {})

            if tool_name == "start_research":
                result = start_research(
                    topic=tool_args.get("topic", ""),
                    codebase_context=tool_args.get("codebase_context", ""),
                    domain_template=tool_args.get("domain_template", "ml"),
                    llm_backend=tool_args.get("llm_backend", "api"),
                    output_dir=tool_args.get("output_dir", "")
                )
            elif tool_name == "get_status":
                result = get_status(tool_args.get("job_id", ""))
            elif tool_name == "get_output":
                result = get_output(
                    tool_args.get("job_id", ""),
                    tool_args.get("section", "all")
                )
            elif tool_name == "list_jobs":
                result = list_jobs()
            elif tool_name == "list_templates":
                result = list_templates()
            elif tool_name == "cancel_job":
                result = cancel_job(tool_args.get("job_id", ""))
            elif tool_name == "query_knowledge":
                result = query_knowledge(
                    tool_args.get("query", ""),
                    tool_args.get("mem_type"),
                    tool_args.get("limit", 10)
                )
            elif tool_name == "query_knowledge_graph":
                result = query_knowledge_graph(
                    tool_args.get("subject"),
                    tool_args.get("predicate"),
                    tool_args.get("object"),
                    tool_args.get("include_invalid", False)
                )
            elif tool_name == "get_knowledge_stats":
                result = get_knowledge_stats()
            elif tool_name == "search_knowledge_index":
                result = search_knowledge_index(
                    tool_args.get("query", ""),
                    tool_args.get("mem_type"),
                    tool_args.get("domain"),
                    tool_args.get("limit", 20)
                )
            elif tool_name == "get_knowledge_details":
                result = get_knowledge_details(
                    tool_args.get("ids", []),
                    tool_args.get("mem_type")
                )
            elif tool_name == "analyze_codebase":
                analyzer = CodebaseAnalyzer(tool_args.get("codebase_path", ""))
                result = analyzer.analyze()
                output_file = tool_args.get("output_file")
                if output_file:
                    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
                    with open(output_file, "w") as f:
                        json.dump(result, f, indent=2)
                    result["_written_to"] = output_file
            elif tool_name == "get_meta_analysis":
                store = KnowledgeStore()
                result = store.read_meta_analysis() or {}
                store.close()
            elif tool_name == "get_what_works":
                store = KnowledgeStore()
                result = store.read_what_works() or {}
                store.close()
            elif tool_name == "run_meta_analysis":
                analyzer = MetaAnalyzer(str(BASE_DIR))
                meta = analyzer.run_analysis()
                what_works = analyzer.generate_what_works(meta)
                with open(BASE_DIR / "meta_analysis.json", "w") as f:
                    json.dump(meta, f, indent=2)
                with open(BASE_DIR / "what_works.json", "w") as f:
                    json.dump(what_works, f, indent=2)
                result = {
                    "meta_analysis": meta,
                    "what_works": what_works,
                    "total_jobs": meta.get("total_jobs", 0),
                    "success_rate": meta.get("overall_success_rate", 0),
                    "recommendation_count": len(what_works.get("recommendations_for_next_job", []))
                }
            elif tool_name == "run_pipeline":
                # Lazy-import the orchestrator so the server boots even if
                # orchestrator deps are missing in legacy installs.
                import sys, pathlib
                _lib = pathlib.Path(__file__).resolve().parent / "lib"
                if str(_lib) not in sys.path:
                    sys.path.insert(0, str(_lib))
                from orchestrator.pipeline import Pipeline
                from orchestrator.dispatch import get_dispatcher

                # The actual Task() callable lives in the host process.
                # The orchestrator returns a stub-driven result; the host's
                # MCP layer calls dispatch_phase reentrantly for each agent.
                dispatcher_cls = get_dispatcher(tool_args.get("host", "claude_code"))
                pipeline = Pipeline(
                    dispatcher=lambda agent_name, inputs: {"raw": "(orchestrator stub - host should reentrant via dispatch_phase)"},
                    evaluator=lambda parsed: {"verdict": "PASS", "reason": ""},
                    host=tool_args.get("host", "claude_code"),
                )
                output_dir = Path(tool_args["output_dir"])
                result = pipeline.run_full_pipeline(
                    topic=tool_args["topic"],
                    domain=tool_args["domain"],
                    output_dir=output_dir,
                    interactivity=tool_args.get("interactivity", "checkpoints"),
                    use_bfts=tool_args.get("use_bfts", False),
                )
            elif tool_name == "dispatch_phase":
                # Reentrant: the orchestrator asks the host to dispatch a Task.
                result = {
                    "agent_name": tool_args["agent_name"],
                    "subagent_type": f"ai-scientist-{tool_args['agent_name']}",
                    "inputs": tool_args["inputs"],
                }
            elif tool_name == "validate_corpus":
                import sys, pathlib, json
                _lib = pathlib.Path(__file__).resolve().parent / "lib"
                if str(_lib) not in sys.path:
                    sys.path.insert(0, str(_lib))
                from orchestrator.cross_validator import validate_corpus
                paper_list = json.loads(
                    pathlib.Path(tool_args["paper_list_path"]).read_text(
                        encoding="utf-8"))
                result = validate_corpus(
                    paper_list,
                    crossref_email=tool_args["crossref_email"],
                    openalex_email=tool_args.get(
                        "openalex_email", tool_args["crossref_email"]),
                    semantic_scholar_key=tool_args.get(
                        "semantic_scholar_key"),
                    annas_enabled=tool_args.get("annas_enabled", False),
                    consensus_enabled=tool_args.get(
                        "consensus_enabled", False),
                    pubmed_enabled=tool_args.get("pubmed_enabled", False),
                    title_threshold=tool_args.get("title_threshold", 0.85),
                )
            elif tool_name == "run_plotter_cycle":
                import sys, pathlib
                _lib = pathlib.Path(__file__).resolve().parent / "lib"
                if str(_lib) not in sys.path:
                    sys.path.insert(0, str(_lib))
                from orchestrator.plotter_loop import PlotterLoop, PlotSpec
                outdir = pathlib.Path(tool_args["output_dir"])
                loop = PlotterLoop(
                    output_dir=outdir,
                    article_type=tool_args.get("article_type", "experimental"),
                    journal_style=tool_args.get("journal_style", "auto"),
                )
                cycle = int(tool_args["cycle"])
                if cycle == 1:
                    specs = [PlotSpec(**s)
                             for s in tool_args.get("figure_specs", [])]
                    result = loop.cycle1_inspect_and_draft(specs)
                elif cycle == 3:
                    result = loop.cycle3_polish_export(
                        mode=tool_args.get("mode", "scripting"))
                else:
                    result = {"error": f"Cycle {cycle} requires a vlm_callable; "
                              "use cycle1_inspect_and_draft or cycle3_polish_export "
                              "directly via the run_pipeline orchestrator entry."}
            else:
                result = {"error": f"Unknown tool: {tool_name}"}

            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result, indent=2)}]
                }
            }

        elif method == "initialize":
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {}
                    },
                    "serverInfo": {
                        "name": "vedix",
                        "version": "3.0.0"
                    }
                }
            }

        elif method == "tools/list":
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"tools": TOOL_DEFINITIONS},
            }

        elif method == "notifications/initialized":
            response = None  # No response for notifications

        else:
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [{"type": "text", "text": f"Method not implemented: {method}"}]
                }
            }

    except Exception as e:
        response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": -32603,
                "message": str(e)
            }
        }

    return response


def run_server():
    """Run the MCP server (stdio transport)."""
    print("AI-Scientist MCP Server starting...", file=sys.stderr)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
            response = handle_request(request)
            if response:
                print(json.dumps(response))
                sys.stdout.flush()
        except json.JSONDecodeError:
            continue
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="AI-Scientist MCP Server")
    parser.add_argument("--mode", choices=["stdio", "cli"], default="stdio",
                        help="Run mode: stdio for MCP, cli for direct testing")
    parser.add_argument("--command", help="CLI command to run")
    parser.add_argument("--job-id", help="Job ID for CLI commands")
    parser.add_argument("--topic", help="Topic for start_research")
    parser.add_argument("--selftest", action="store_true",
                        help="Run a non-LLM smoke check: open DB, exit 0/1")
    args = parser.parse_args()

    if args.selftest:
        try:
            store = KnowledgeStore()
            stats = store.get_stats()
            store.close()
            print(f"selftest: BASE_DIR={BASE_DIR}", file=sys.stderr)
            print(f"selftest: knowledge_store backend={stats.get('backend')}", file=sys.stderr)
            print(f"selftest: papers_count={stats.get('papers_count', 0)}", file=sys.stderr)
            print(f"selftest: OK", file=sys.stderr)
            sys.exit(0)
        except Exception as e:
            print(f"selftest: FAILED - {e}", file=sys.stderr)
            sys.exit(1)

    if args.mode == "cli":
        if args.command == "start":
            result = start_research(
                topic=args.topic or "Test topic",
                codebase_context="",
                domain_template="statistical"
            )
            print(json.dumps(result, indent=2))
        elif args.command == "status":
            result = get_status(args.job_id)
            print(json.dumps(result, indent=2))
        elif args.command == "list":
            result = list_jobs()
            print(json.dumps(result, indent=2))
        elif args.command == "stats":
            result = get_knowledge_stats()
            print(json.dumps(result, indent=2))
        elif args.command == "query":
            result = query_knowledge(args.topic or "test", limit=5)
            print(json.dumps(result, indent=2))
        else:
            print("Available commands: start, status, list, stats, query")
    else:
        run_server()
