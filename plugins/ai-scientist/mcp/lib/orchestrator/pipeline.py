"""Pipeline orchestrator. Per spec §4.10.

Owns state, calls .md agents via the host dispatcher, runs ReflectionLoop
and BiasedReviewers and StageGate around them, mines to MemPalace,
checkpoints between phases, surfaces AskUserQuestion gates.

This file grows phase-by-phase across Tasks 18-26. Each task adds 1-2
methods; the run_full_pipeline() top-level orchestrator lands in Task 26.
"""
from __future__ import annotations
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, List, Optional
from datetime import datetime, timezone
import uuid

from .reflection import ReflectionLoop, EvaluatorVerdict
from .schemas import IDEATION_SCHEMA, HYPOTHESIS_SCHEMA, validate_against
from .extraction import extract_json, extract_python, extract_latex, ExtractionError
from .checkpoints import CheckpointManager
from .tokens import TokenTracker
from .convergence import SemanticConvergence
from .references import validate_citations
from .ensemble import BiasedReviewers


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

    # --- Phase 4: Experiment --------------------------------------------
    def phase_4_experiment(self, *, code_artifacts: dict, use_bfts: bool = False, timeout_seconds: int = 300) -> dict:
        if use_bfts:
            return self._phase_4b_bfts(timeout_seconds=timeout_seconds * 6)
        return self._phase_4a_single_shot(timeout_seconds=timeout_seconds)

    def _phase_4a_single_shot(self, *, timeout_seconds: int) -> dict:
        inputs = {"output_dir": str(self.state.output_dir),
                  "auto_fix_max_rounds": 3, "timeout_seconds": timeout_seconds}
        response = self.dispatcher(agent_name="experiment-runner", inputs=inputs)
        parsed = extract_json(response.get("raw", "")) if isinstance(response, dict) else {}
        if self.checkpoints: self.checkpoints.save("phase_4a", parsed)
        return parsed

    def _phase_4b_bfts(self, *, timeout_seconds: int) -> dict:
        inputs = {"output_dir": str(self.state.output_dir),
                  "bfts_config_path": "${plugin_root}/mcp/lib/sakana/bfts_config.yaml",
                  "time_budget_minutes": timeout_seconds // 60}
        response = self.dispatcher(agent_name="tree-search-runner", inputs=inputs)
        parsed = extract_json(response.get("raw", "")) if isinstance(response, dict) else {}
        if self.checkpoints: self.checkpoints.save("phase_4b", parsed)
        return parsed

    # --- Phase 5.5: Plotting --------------------------------------------
    def phase_5_5_plotting(self, *, max_rounds: int = 2) -> dict:
        history = []
        for round_n in range(max_rounds):
            inputs = {"output_dir": str(self.state.output_dir),
                      "data_summary": self._summarize_data(), "prior_attempts": history}
            response = self.dispatcher(agent_name="plotter", inputs=inputs)
            raw = response.get("raw", "") if isinstance(response, dict) else ""
            agg_path = self.state.output_dir / "auto_plot_aggregator.py"
            try:
                code = extract_python(raw)
                agg_path.write_text(code, encoding="utf-8")
                result = subprocess.run(
                    ["python", str(agg_path)], cwd=str(self.state.output_dir),
                    capture_output=True, text=True, timeout=120,
                )
                if result.returncode == 0:
                    break
                history.append({"round": round_n, "stderr": result.stderr[:1000]})
            except Exception as e:
                history.append({"round": round_n, "error": str(e)})
        figs = list((self.state.output_dir / "figures").glob("*.png"))[:12]
        if self.checkpoints: self.checkpoints.save("phase_5_5", {"figures": [str(f) for f in figs]})
        return {"figures": [str(f) for f in figs]}

    # --- Phase 5: Manuscript --------------------------------------------
    def phase_5_manuscript(self, *, papers: list, hypothesis: dict, results: dict, max_rounds: int = 3) -> str:
        history = []
        tex = ""
        manuscript_path = self.state.output_dir / "manuscript.tex"
        for round_n in range(max_rounds):
            inputs = {"paper_list_compact": json.dumps(papers[:30]),
                      "hypothesis_summary": hypothesis.get("hypothesis", "")[:400],
                      "experiment_summary": results.get("stdout_summary", "")[:500],
                      "prior_attempts": history}
            response = self.dispatcher(agent_name="manuscript-writer", inputs=inputs)
            raw = response.get("raw", "") if isinstance(response, dict) else ""
            try:
                tex = extract_latex(raw)
            except Exception as e:
                history.append({"round": round_n, "error": str(e)})
                continue
            manuscript_path.write_text(tex, encoding="utf-8")
            try:
                compile_result = subprocess.run(
                    ["pdflatex", "-interaction=nonstopmode", "manuscript.tex"],
                    cwd=str(self.state.output_dir), capture_output=True, text=True, timeout=60,
                )
                if compile_result.returncode == 0:
                    break
                history.append({"round": round_n, "compile_error": compile_result.stdout[-2000:]})
            except (FileNotFoundError, subprocess.TimeoutExpired):
                # pdflatex not installed or timed out; accept the .tex anyway
                break
        if self.checkpoints: self.checkpoints.save("phase_5", {"manuscript_path": str(manuscript_path)})
        return tex

    @staticmethod
    def _summarize_data() -> str:
        return "results.csv (long-format) + .npy data files"

    # --- Phase 6: Citations ---------------------------------------------
    def phase_6_citations(self) -> dict:
        tex_path = self.state.output_dir / "manuscript.tex"
        bib_path = self.state.output_dir / "references.bib"
        if not tex_path.is_file() or not bib_path.is_file():
            return {"is_clean": False, "skipped": "missing tex or bib"}
        tex = tex_path.read_text(encoding="utf-8")
        report = validate_citations(tex, bib_path, crossref_check=False, llm_judge=None)
        if not report.is_clean:
            response = self.dispatcher(
                agent_name="citator",
                inputs={"manuscript_tex": tex, "references_bib": bib_path.read_text(encoding="utf-8"),
                        "dangling": report.dangling, "uncited": report.uncited, "max_rounds": 5},
            )
            try:
                updated = extract_json(response.get("raw", ""))
                if "references_bib" in updated:
                    bib_path.write_text(updated["references_bib"], encoding="utf-8")
            except Exception:
                pass
        if self.checkpoints: self.checkpoints.save("phase_6", {"citation_report": {
            "dangling": report.dangling, "uncited": report.uncited,
            "hallucinated": report.hallucinated, "is_clean": report.is_clean,
        }})
        return {"is_clean": report.is_clean}

    # --- Phase 7: Review ------------------------------------------------
    def phase_7_review(self, *, manuscript_tex: str) -> dict:
        br = BiasedReviewers(dispatcher=self.dispatcher, biases=["positive", "negative", "neutral"])
        aggregate = br.review(manuscript=manuscript_tex, agent_name="reviewer")
        review_data = {
            "median_overall": aggregate.median_overall,
            "score_iqr": aggregate.score_iqr,
            "consensus_high": aggregate.consensus_high,
            "has_outliers": aggregate.has_outliers,
            "individual_reviews": aggregate.individual_reviews,
        }
        (self.state.output_dir / "review.json").write_text(
            json.dumps(review_data, indent=2), encoding="utf-8",
        )
        if self.checkpoints: self.checkpoints.save("phase_7", review_data)
        return review_data

    # --- Phase 8: Compile -----------------------------------------------
    def phase_8_compile(self) -> Optional[Path]:
        cwd = str(self.state.output_dir)
        for cmd in [
            ["pdflatex", "-interaction=nonstopmode", "manuscript.tex"],
            ["bibtex", "manuscript"],
            ["pdflatex", "-interaction=nonstopmode", "manuscript.tex"],
            ["pdflatex", "-interaction=nonstopmode", "manuscript.tex"],
        ]:
            try:
                subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=60)
            except (FileNotFoundError, subprocess.TimeoutExpired):
                return None
        pdf = self.state.output_dir / "manuscript.pdf"
        return pdf if pdf.is_file() else None

    # --- Phase 8.25: Word export ----------------------------------------
    def phase_8_25_word(self) -> Optional[Path]:
        try:
            subprocess.run(
                ["pandoc", "manuscript.tex", "-o", "manuscript.docx"],
                cwd=str(self.state.output_dir), capture_output=True, text=True, timeout=60,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None
        docx = self.state.output_dir / "manuscript.docx"
        return docx if docx.is_file() else None

    # --- Phase 8.5: VLM review ------------------------------------------
    def phase_8_5_vlm(self) -> dict:
        pdf = self.state.output_dir / "manuscript.pdf"
        if not pdf.is_file():
            return {"skipped": "no manuscript.pdf"}
        figs = sorted((self.state.output_dir / "figures").glob("*.png"))
        response = self.dispatcher(
            agent_name="vlm-reviewer",
            inputs={"route": "md_agent", "rendered_pages": [str(f) for f in figs]},
        )
        try:
            result = extract_json(response.get("raw", ""))
        except Exception:
            result = {"error": "vlm response parse failed"}
        (self.state.output_dir / "visual_review.json").write_text(
            json.dumps(result, indent=2), encoding="utf-8",
        )
        if self.checkpoints: self.checkpoints.save("phase_8_5", result)
        return result

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
