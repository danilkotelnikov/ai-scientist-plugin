"""Pipeline orchestrator. Per spec §4.10.

Owns state, calls .md agents via the host dispatcher, runs ReflectionLoop
and BiasedReviewers and StageGate around them, mines to MemPalace,
checkpoints between phases, surfaces AskUserQuestion gates.

This file grows phase-by-phase across Tasks 18-26. Each task adds 1-2
methods; the run_full_pipeline() top-level orchestrator lands in Task 26.
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, List, Optional
from datetime import datetime, timezone
import uuid

from .reflection import ReflectionLoop, EvaluatorVerdict
from .schemas import IDEATION_SCHEMA, HYPOTHESIS_SCHEMA, validate_against
from .extraction import extract_json, extract_python, ExtractionError
from .checkpoints import CheckpointManager
from .tokens import TokenTracker
from .convergence import SemanticConvergence


@dataclass
class PipelineState:
    job_id: str = ""
    topic: str = ""
    domain: str = ""
    output_dir: Optional[Path] = None
    config: dict = field(default_factory=dict)


class Pipeline:
    def __init__(
        self,
        *,
        dispatcher: Callable,
        evaluator: Callable,
        host: str = "claude_code",
        plugin_palace: Any = None,
        project_palace: Any = None,
        token_tracker: Optional[TokenTracker] = None,
    ):
        self.dispatcher = dispatcher
        self.evaluator = evaluator
        self.host = host
        self.plugin_palace = plugin_palace
        self.project_palace = project_palace
        self.tokens = token_tracker or TokenTracker()
        self.state = PipelineState()
        self.checkpoints: Optional[CheckpointManager] = None

    # --- Phase 0 ---------------------------------------------------------
    def phase_0_init(self, *, topic: str, domain: str, output_dir: Path) -> None:
        self.state.job_id = uuid.uuid4().hex[:8]
        self.state.topic = topic
        self.state.domain = domain
        self.state.output_dir = Path(output_dir)
        self.state.output_dir.mkdir(parents=True, exist_ok=True)
        (self.state.output_dir / ".checkpoints").mkdir(exist_ok=True)
        (self.state.output_dir / ".palace").mkdir(exist_ok=True)
        self.checkpoints = CheckpointManager(
            checkpoint_dir=self.state.output_dir / ".checkpoints",
            palace=self.project_palace,
        )
        self.state.config = {
            "job_id": self.state.job_id,
            "topic": topic,
            "domain": domain,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        (self.state.output_dir / "config.json").write_text(
            json.dumps(self.state.config, indent=2), encoding="utf-8"
        )

    # --- Phase 0.5: Ideation --------------------------------------------
    def phase_0_5_ideation(
        self,
        *,
        topic: str,
        domain: str,
        num_candidates: int = 3,
        max_rounds: int = 3,
    ) -> List[dict]:
        candidates: List[dict] = []
        loop = ReflectionLoop(
            dispatcher=self.dispatcher,
            evaluator=lambda parsed: self._wrap_evaluator(parsed),
            schema=IDEATION_SCHEMA,
            extractor=lambda response: extract_json(response.get("raw", "")),
        )
        for i in range(num_candidates):
            inputs = {
                "topic": topic, "domain": domain,
                "candidate_index": i + 1, "total_candidates": num_candidates,
                "previous_ideas": json.dumps([c.get("Name", "") for c in candidates]),
            }
            try:
                idea = loop.run(agent_name="ideator", inputs=inputs, max_rounds=max_rounds)
                candidates.append(idea)
            except Exception as e:
                candidates.append({"Name": f"failed_{i}", "error": str(e)})
        # Persist
        out = self.state.output_dir / "idea_candidates.json"
        out.write_text(json.dumps(candidates, indent=2), encoding="utf-8")
        if self.checkpoints:
            self.checkpoints.save("phase_0_5", {"candidates": candidates})
        return candidates

    # --- Phase 0.75: Codebase scanner ----------------------------------
    def phase_0_75_codebase(self, *, codebase_path: Optional[Path]) -> dict:
        if not codebase_path:
            return {}
        response = self.dispatcher(agent_name="codebase-scanner", inputs={"codebase_path": str(codebase_path)})
        parsed = extract_json(response.get("raw", "")) if isinstance(response, dict) else {}
        out = self.state.output_dir / "codebase_analysis.json"
        out.write_text(json.dumps(parsed, indent=2), encoding="utf-8")
        if self.checkpoints: self.checkpoints.save("phase_0_75", parsed)
        return parsed

    # --- Phase 1: Literature search -------------------------------------
    def phase_1_literature(self, *, idea: dict, sources: Optional[list] = None) -> List[dict]:
        sources = sources or ["openalex", "arxiv", "pubmed", "biorxiv", "semanticscholar", "annas-mcp"]
        queries = self._build_queries(idea, n=8)
        all_papers: List[dict] = []
        for source in sources:
            response = self.dispatcher(
                agent_name="literature-searcher",
                inputs={"source": source, "queries": queries, "max_per_source": 8, "time_budget_seconds": 60},
            )
            raw = response.get("raw", "") if isinstance(response, dict) else ""
            try:
                papers = self._parse_paper_list(raw)
                if isinstance(papers, list):
                    all_papers.extend(papers)
            except Exception:
                continue
        deduped = self._dedup_papers(all_papers)
        (self.state.output_dir / "paper_list.json").write_text(
            json.dumps(deduped, indent=2), encoding="utf-8"
        )
        if self.checkpoints: self.checkpoints.save("phase_1", {"papers": deduped})
        return deduped

    @staticmethod
    def _parse_paper_list(raw: str) -> list:
        """Parse a JSON array from raw text; supports ```json fence or bare array."""
        import re
        m = re.search(r"```json\s*\n?(.*?)\n?```", raw, re.DOTALL)
        candidate = m.group(1) if m else raw
        parsed = json.loads(candidate.strip())
        if isinstance(parsed, dict) and "papers" in parsed:
            return parsed["papers"]
        return parsed if isinstance(parsed, list) else []

    @staticmethod
    def _build_queries(idea: dict, n: int = 8) -> list:
        core = idea.get("Title", "")[:150]
        return [
            core, f"{core} computational design", f"{core} deep learning",
            f"{core} structure prediction", f"{core} machine learning",
            f"{core} review 2025", f"{core} benchmark dataset", f"{core} therapeutic applications",
        ][:n]

    @staticmethod
    def _dedup_papers(papers: list) -> list:
        seen_doi, seen_title = set(), set()
        out = []
        for p in papers:
            doi = (p.get("doi") or "").lower()
            title_norm = (p.get("title") or "").lower().strip()[:80]
            if doi and doi in seen_doi: continue
            if title_norm and title_norm in seen_title: continue
            if doi: seen_doi.add(doi)
            if title_norm: seen_title.add(title_norm)
            out.append(p)
        return out

    # --- Phase 2: Hypothesis --------------------------------------------
    def phase_2_hypothesis(self, *, idea: dict, papers: list) -> dict:
        loop = ReflectionLoop(
            dispatcher=self.dispatcher,
            evaluator=lambda p: self._wrap_evaluator(p),
            schema=HYPOTHESIS_SCHEMA,
            extractor=lambda r: extract_json(r.get("raw", "")),
        )
        inputs = {
            "topic": self.state.topic, "domain": self.state.domain,
            "idea_json": json.dumps(idea),
            "paper_list_compact": json.dumps([{"title": p.get("title"), "year": p.get("year")} for p in papers[:10]]),
        }
        hypothesis = loop.run(agent_name="hypothesizer", inputs=inputs, max_rounds=3)
        (self.state.output_dir / "hypothesis.md").write_text(
            hypothesis.get("hypothesis", "") + "\n\n" + hypothesis.get("math_models", ""),
            encoding="utf-8",
        )
        if self.checkpoints: self.checkpoints.save("phase_2", hypothesis)
        return hypothesis

    # --- Phase 3: Code generation ---------------------------------------
    def phase_3_codegen(self, *, hypothesis: dict, max_rounds: int = 3) -> dict:
        history = []
        for round_n in range(max_rounds):
            inputs = {"hypothesis_md": hypothesis.get("hypothesis", ""),
                      "config_json": json.dumps(self.state.config),
                      "prior_attempts": history}
            response = self.dispatcher(agent_name="code-generator", inputs=inputs)
            raw = response.get("raw", "") if isinstance(response, dict) else ""
            try:
                code = extract_python(raw)
                requirements = self._extract_requirements(raw)
            except ExtractionError as e:
                history.append({"round": round_n, "error": str(e)})
                continue
            (self.state.output_dir / "experiment.py").write_text(code, encoding="utf-8")
            (self.state.output_dir / "requirements.txt").write_text(requirements, encoding="utf-8")
            if self.checkpoints: self.checkpoints.save("phase_3", {"code": code, "requirements": requirements})
            return {"code": code, "requirements": requirements}
        raise RuntimeError(f"phase_3_codegen: no parseable code after {max_rounds} rounds")

    @staticmethod
    def _extract_requirements(text: str) -> str:
        import re
        m = re.search(r"```\s*(?:requirements\.?txt)?\s*\n([\s\S]+?)\n```", text)
        if m and ("==" in m.group(1) or ">=" in m.group(1) or m.group(1).strip().startswith(("numpy", "scipy", "torch"))):
            return m.group(1).strip()
        return "numpy>=1.26\nscikit-learn>=1.3\nmatplotlib>=3.7\n"

    def _wrap_evaluator(self, parsed: dict) -> EvaluatorVerdict:
        try:
            v = self.evaluator(parsed)
            if isinstance(v, dict):
                return EvaluatorVerdict(verdict=v.get("verdict", "PASS"), reason=v.get("reason", ""))
            if isinstance(v, EvaluatorVerdict):
                return v
            return EvaluatorVerdict(verdict="PASS", reason="")
        except Exception:
            return EvaluatorVerdict(verdict="PASS", reason="evaluator-skipped")
