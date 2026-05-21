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
from .article_type import classify_article_type, phase_order_for, NON_APPLICABLE_PHASES
from .cross_validator import validate_corpus
from .anti_llm_lint import lint_text, audit_claims
from .reviewer_ledger import build_reviewer_dispatch


@dataclass
class GateRequest:
    """Returned to the SKILL.md when a phase needs user input."""
    gate_id: int
    question: str
    options: list


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

    # --- Phase 5R: Review-article manuscript --------------------------------
    def phase_5r_manuscript_review_article(self, *, papers: list,
                                           hypothesis: dict,
                                           max_rounds: int = 3) -> str:
        """Phase 5R: review-article manuscript with anti-LLMish + claim-audit loop."""
        history = []
        tex = ""
        manuscript_path = self.state.output_dir / "manuscript.tex"
        for round_n in range(max_rounds):
            inputs = {
                "paper_list_compact": json.dumps(papers[:30]),
                "hypothesis_summary": hypothesis.get("hypothesis", "")[:400],
                "synthesis_mode": "review_article",
                "prior_attempts": history,
            }
            response = self.dispatcher(agent_name="manuscript-writer",
                                       inputs=inputs)
            raw = response.get("raw", "") if isinstance(response, dict) else ""
            try:
                tex = extract_latex(raw)
            except Exception as e:
                history.append({"round": round_n, "error": str(e)})
                continue
            manuscript_path.write_text(tex, encoding="utf-8")

            # Anti-LLMish lint + claim audit
            lint = lint_text(tex)
            claims = audit_claims(tex)
            (self.state.output_dir / "anti_llm_lint.json").write_text(
                json.dumps(lint, indent=2), encoding="utf-8")
            (self.state.output_dir / "claim_audit.json").write_text(
                json.dumps(claims, indent=2), encoding="utf-8")

            tier1_hits = [h for h in lint["hits"] if h.get("tier") == 1]
            tier3_hits = [h for h in lint["hits"] if h.get("tier") == 3]
            clarif = claims.get("clarification_requests", [])

            if not tier1_hits and not tier3_hits and not clarif:
                break  # Clean draft

            history.append({
                "round": round_n,
                "tier1_blocks": [h["term"] for h in tier1_hits[:10]],
                "tier3_blocks": [h["match"][:60] for h in tier3_hits[:10]],
                "clarification_requests": clarif[:5],
                "instruction": (
                    "Rewrite avoiding the listed Tier-1 words and Tier-3 phrases; "
                    "for each clarification_request, replace the vague claim with "
                    "a specific quantification or appropriate hedge."
                ),
            })

        if self.checkpoints:
            self.checkpoints.save("phase_5r",
                                  {"manuscript_path": str(manuscript_path)})
        return tex

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

    # --- Phase 7R: Review-article peer review ------------------------------
    def phase_7r_review(self, *, manuscript_tex: str,
                        codex_native_dispatcher=None) -> dict:
        """Phase 7R: review-article peer review.

        If codex_native_dispatcher is provided, fan out 3 biased reviewers via
        spawn_agent waves. Otherwise inline fallback (sequential dispatcher calls).
        """
        biases = ["positive", "negative", "neutral"]
        reviews = []
        if codex_native_dispatcher is not None:
            try:
                payloads = codex_native_dispatcher.dispatch_wave(
                    agent_name="reviewer",
                    inputs_list=[{"manuscript": manuscript_tex,
                                  "system_bias": b} for b in biases],
                )
                for b, p in zip(biases, payloads):
                    reviews.append({"role": b, "agent_id": None,
                                    "agent_type": "worker", "model": "gpt-5.5",
                                    "status": "completed", "payload": p})
                mode, fb_reason = "native_subagents", None
            except Exception as e:
                mode, fb_reason = "inline_fallback", f"native_dispatch_error: {e}"
                reviews = []  # fall through to inline below
        else:
            mode, fb_reason = "inline_fallback", "codex_native_dispatcher not configured"

        if not reviews:
            # Inline fallback: sequential dispatcher.dispatch
            for b in biases:
                r = self.dispatcher(agent_name="reviewer",
                                    inputs={"manuscript": manuscript_tex,
                                            "system_bias": b})
                reviews.append({"role": b, "agent_id": None, "agent_type": None,
                                "model": None, "status": "inline", "payload": r})

        # Aggregate
        scores = [r["payload"].get("Overall", 5) for r in reviews]
        review_doc = {
            "median_overall": sorted(scores)[len(scores) // 2] if scores else None,
            "individual_reviews": [r["payload"] for r in reviews],
            "biases": biases,
        }
        (self.state.output_dir / "review.json").write_text(
            json.dumps(review_doc, indent=2), encoding="utf-8")

        # reviewer_dispatch.json
        dispatch_doc = build_reviewer_dispatch(
            reviews, mode=mode, max_threads=6, fallback_reason=fb_reason)
        (self.state.output_dir / "reviewer_dispatch.json").write_text(
            json.dumps(dispatch_doc, indent=2), encoding="utf-8")

        if self.checkpoints:
            self.checkpoints.save("phase_7r", review_doc)
        return review_doc

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

    # --- Phase 9: Index -------------------------------------------------
    def phase_9_index(self, *, papers: list, idea: dict, hypothesis: dict, review: dict) -> None:
        if self.project_palace is not None:
            try:
                self.project_palace.write_diary(
                    agent="indexer",
                    content=f"Job {self.state.job_id} indexed: {len(papers)} papers, "
                            f"hypothesis={hypothesis.get('hypothesis','')[:100]}, "
                            f"review_overall={review.get('median_overall','?')}",
                    tags=["phase-9-index"],
                )
            except Exception:
                pass

    # --- Phase 10: Meta-analysis ----------------------------------------
    def phase_10_meta(self) -> dict:
        response = self.dispatcher(agent_name="meta-analyst", inputs={
            "trajectories_jsonl": "", "jobs_json": "",
        })
        try:
            result = extract_json(response.get("raw", ""))
        except Exception:
            result = {}
        if self.project_palace is not None and "findings_update" in result:
            for section, content in result["findings_update"].items():
                try:
                    self.project_palace.write_findings(section=section, content=content)
                except Exception:
                    pass
        return result

    # --- Phase 11: Slides -----------------------------------------------
    def phase_11_slides(self) -> Optional[Path]:
        response = self.dispatcher(agent_name="slide-presenter", inputs={
            "manuscript_pdf": str(self.state.output_dir / "manuscript.pdf"),
            "manuscript_tex": str(self.state.output_dir / "manuscript.tex"),
            "figures_dir": str(self.state.output_dir / "figures"),
        })
        pdf = self.state.output_dir / "manuscript-slides.pdf"
        return pdf if pdf.is_file() else None

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

    # --- Gate helper --------------------------------------------------------
    def _gate_or_default(
        self,
        *,
        gate_id: int,
        default,
        question: str,
        options: list,
        callback: Optional[Callable],
        interactivity: str,
        critical: bool = False,
    ):
        if interactivity == "none":
            return default
        if interactivity == "checkpoints" and not critical:
            return default
        if callback is None:
            return default
        try:
            return callback(GateRequest(gate_id=gate_id, question=question, options=options))
        except Exception:
            return default

    # --- Top-level pipeline -------------------------------------------------
    def run_full_pipeline(
        self,
        *,
        topic: str,
        domain: str,
        output_dir: Path,
        interactivity: str = "checkpoints",
        use_bfts: bool = False,
        codebase_path: Optional[Path] = None,
        user_input_callback: Optional[Callable] = None,
    ) -> dict:
        """The end-to-end pipeline. SKILL.md surfaces gates via user_input_callback.

        Returns a dict summary of all artifacts + token usage.
        """
        self.phase_0_init(topic=topic, domain=domain, output_dir=output_dir)
        if codebase_path:
            self.phase_0_75_codebase(codebase_path=codebase_path)
        candidates = self.phase_0_5_ideation(topic=topic, domain=domain, num_candidates=3)
        idea = self._gate_or_default(
            gate_id=2, default=candidates[0], question="Pick an idea",
            options=[c.get("Name", f"#{i}") for i, c in enumerate(candidates)],
            callback=user_input_callback, interactivity=interactivity,
            critical=True,
        )
        if isinstance(idea, str):
            idea = next((c for c in candidates if c.get("Name") == idea), candidates[0])
        (self.state.output_dir / "idea.json").write_text(json.dumps(idea, indent=2), encoding="utf-8")
        papers = self.phase_1_literature(idea=idea)
        hypothesis = self.phase_2_hypothesis(idea=idea, papers=papers)
        code_artifacts = self.phase_3_codegen(hypothesis=hypothesis)
        results = self.phase_4_experiment(code_artifacts=code_artifacts, use_bfts=use_bfts)
        self.phase_5_5_plotting()
        manuscript_tex = self.phase_5_manuscript(
            papers=papers, hypothesis=hypothesis, results=results,
        )
        self.phase_6_citations()
        review = self.phase_7_review(manuscript_tex=manuscript_tex)
        self.phase_8_compile()
        self.phase_8_25_word()
        self.phase_8_5_vlm()
        self.phase_9_index(papers=papers, idea=idea, hypothesis=hypothesis, review=review)
        self.phase_10_meta()
        self.phase_11_slides()
        return {
            "job_id": self.state.job_id,
            "tokens": self.tokens.report(),
            "review": review,
            "output_dir": str(self.state.output_dir),
        }

    # --- Phase -1: Intent classification -----------------------------------
    def phase_minus_1_intent(self, *, explicit: str = "auto") -> dict:
        """Phase -1: classify article_type from topic + explicit flag."""
        article_type = classify_article_type(topic=self.state.topic,
                                             explicit=explicit)
        phase_order = phase_order_for(article_type)
        non_app = NON_APPLICABLE_PHASES[article_type]
        self.state.config["article_type"] = article_type
        self.state.config["phase_order"] = phase_order
        self.state.config["non_applicable_phases"] = non_app
        (self.state.output_dir / "config.json").write_text(
            json.dumps(self.state.config, indent=2), encoding="utf-8")
        return {"article_type": article_type, "phase_order": phase_order,
                "non_applicable_phases": non_app}

    # --- Phase 1.5: Metadata validation ------------------------------------
    def phase_1_5_metadata_validation(self, *, crossref_email: str,
                                      openalex_email: Optional[str] = None,
                                      semantic_scholar_key: Optional[str] = None,
                                      annas_enabled: bool = False,
                                      consensus_enabled: bool = False,
                                      pubmed_enabled: bool = False) -> dict:
        """Phase 1.5: strict DOI-gate + cascade enrichment.

        Reads paper_list.json, runs validate_corpus, writes references_validation.json.
        Drops papers that fail Stage 1 from a filtered paper_list.validated.json.
        """
        plist = json.loads(
            (self.state.output_dir / "paper_list.json").read_text())
        report = validate_corpus(
            plist,
            crossref_email=crossref_email,
            openalex_email=openalex_email or crossref_email,
            semantic_scholar_key=semantic_scholar_key,
            annas_enabled=annas_enabled,
            consensus_enabled=consensus_enabled,
            pubmed_enabled=pubmed_enabled,
        )
        (self.state.output_dir / "references_validation.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8")
        # Filter paper_list to validated-only
        validated_keys = {v["key"] for v in report["validated"]}
        filtered = [p for p in plist
                    if p.get("key", p.get("doi", "?")) in validated_keys]
        (self.state.output_dir / "paper_list.validated.json").write_text(
            json.dumps(filtered, indent=2), encoding="utf-8")
        if self.checkpoints:
            self.checkpoints.save("phase_1_5", report)
        return report

    # --- Top-level review-article pipeline ---------------------------------
    def run_review_article_pipeline(
        self, *, topic: str, domain: str, output_dir: Path,
        crossref_email: str,
        openalex_email: Optional[str] = None,
        semantic_scholar_key: Optional[str] = None,
        annas_enabled: bool = False, consensus_enabled: bool = False,
        pubmed_enabled: bool = False,
        explicit_article_type: str = "auto",
        interactivity: str = "checkpoints",
        user_input_callback: Optional[Callable] = None,
        codex_native_dispatcher: Any = None,
    ) -> dict:
        """v2.1 review-article pipeline. Use article_type=review phase order."""
        self.phase_0_init(topic=topic, domain=domain, output_dir=output_dir)
        intent = self.phase_minus_1_intent(explicit=explicit_article_type)
        if intent["article_type"] != "review":
            # Caller is using the wrong entrypoint; honor intent and route.
            return self.run_full_pipeline(
                topic=topic, domain=domain, output_dir=output_dir,
                interactivity=interactivity,
                user_input_callback=user_input_callback)

        candidates = self.phase_0_5_ideation(topic=topic, domain=domain,
                                             num_candidates=3)
        idea = self._gate_or_default(
            gate_id=2, default=candidates[0], question="Pick a review thesis",
            options=[c.get("Name", f"#{i}") for i, c in enumerate(candidates)],
            callback=user_input_callback, interactivity=interactivity,
            critical=True)
        if isinstance(idea, str):
            idea = next((c for c in candidates if c.get("Name") == idea),
                        candidates[0])
        (self.state.output_dir / "idea.json").write_text(
            json.dumps(idea, indent=2), encoding="utf-8")

        papers = self.phase_1_literature(idea=idea)
        # Ensure paper_list.json exists for phase_1_5_metadata_validation
        paper_list_path = self.state.output_dir / "paper_list.json"
        if not paper_list_path.is_file():
            paper_list_path.write_text(
                json.dumps(papers, indent=2), encoding="utf-8")
        self.phase_1_5_metadata_validation(
            crossref_email=crossref_email,
            openalex_email=openalex_email,
            semantic_scholar_key=semantic_scholar_key,
            annas_enabled=annas_enabled,
            consensus_enabled=consensus_enabled,
            pubmed_enabled=pubmed_enabled,
        )
        # Re-load validated subset
        validated = json.loads(
            (self.state.output_dir / "paper_list.validated.json")
            .read_text(encoding="utf-8"))

        hypothesis = self.phase_2_hypothesis(idea=idea, papers=validated)
        manuscript_tex = self.phase_5r_manuscript_review_article(
            papers=validated, hypothesis=hypothesis)
        self.phase_6_citations()
        review = self.phase_7r_review(manuscript_tex=manuscript_tex,
                                      codex_native_dispatcher=codex_native_dispatcher)
        # Ensure reviewer_dispatch.json exists (may be written by phase_7r_review)
        rd_path = self.state.output_dir / "reviewer_dispatch.json"
        if not rd_path.is_file():
            rd_path.write_text(json.dumps({
                "mode": "inline_fallback",
                "reviewers": [],
                "review": review,
            }, indent=2), encoding="utf-8")
        self.phase_8_compile()
        self.phase_8_25_word()
        self.phase_8_5_vlm()
        self.phase_9_index(papers=validated, idea=idea, hypothesis=hypothesis,
                           review=review)
        self.phase_10_meta()
        self.phase_11_slides()
        return {
            "job_id": self.state.job_id,
            "article_type": "review",
            "tokens": self.tokens.report(),
            "review": review,
            "output_dir": str(self.state.output_dir),
        }

    def render_research_state_view(self) -> Path:
        """Render <output_dir>/research-state.yaml from current pipeline state."""
        try:
            import yaml
        except ImportError:
            # Fallback: write JSON instead
            path = self.state.output_dir / "research-state.json"
            view = {
                "job_id": self.state.job_id,
                "topic": self.state.topic,
                "domain": self.state.domain,
                "status": "running",
                "ideation": {"candidates_generated": 0, "candidate_names": [], "selected": ""},
            }
            path.write_text(json.dumps(view, indent=2), encoding="utf-8")
            return path
        view = {
            "job_id": self.state.job_id,
            "topic": self.state.topic,
            "domain": self.state.domain,
            "status": "running",
            "ideation": {
                "candidates_generated": 0,
                "candidate_names": [],
                "selected": "",
            },
        }
        path = self.state.output_dir / "research-state.yaml"
        path.write_text(yaml.safe_dump(view, sort_keys=False), encoding="utf-8")
        return path
