from __future__ import annotations
import json
import time
from typing import Optional
from ..dispatch import dispatch_agent
from .kg_store import KGStore
from .schema import SentenceBucket, VerifierResult


class ClaimVerifier:
    def __init__(self, *, store: KGStore, max_retries: int = 3):
        self.store = store
        self.max_retries = max_retries

    async def verify(self, sentence: SentenceBucket) -> SentenceBucket:
        """Returns the same sentence with `verifier` populated."""
        if sentence.bucket == "cite":
            result = await self._verify_cite(sentence)
        elif sentence.bucket == "synthesize":
            result = await self._verify_synthesize(sentence)
        elif sentence.bucket == "speculate":
            result = self._verify_speculate(sentence)
        else:
            result = VerifierResult(status="fail-bucket",
                                    rationale=f"unknown bucket {sentence.bucket!r}",
                                    ran_at_ts=time.time())
        sentence.verifier = result
        return sentence

    async def _verify_cite(self, sentence: SentenceBucket) -> VerifierResult:
        anchor_id = sentence.anchors[0].node_id if sentence.anchors else None
        if anchor_id is None:
            return VerifierResult(status="fail-bucket",
                                  rationale="cite bucket requires at least one anchor",
                                  ran_at_ts=time.time())
        claim = self._find_claim(anchor_id)
        if claim is None:
            return VerifierResult(status="fail-bucket",
                                  rationale=f"anchor not found in KG: {anchor_id}",
                                  ran_at_ts=time.time())
        verdict = await self._llm_entailment(
            sentence_text=sentence.text,
            anchor_quote=claim.verbatim_quote,
            anchor_paraphrase=claim.paraphrase,
        )
        status_str = verdict.get("status", "fail-entailment")
        return VerifierResult(
            status=status_str if status_str in ("pass", "fail-entailment") else "fail-entailment",
            entailment_score=float(verdict.get("score", 0.0)),
            rationale=verdict.get("rationale", ""),
            ran_at_ts=time.time(),
        )

    async def _verify_synthesize(self, sentence: SentenceBucket) -> VerifierResult:
        if len(sentence.anchors) < 2:
            return VerifierResult(status="fail-bucket",
                                  rationale="synthesize requires >= 2 anchors",
                                  ran_at_ts=time.time())
        anchor_claims = []
        for a in sentence.anchors:
            c = self._find_claim(a.node_id)
            if c is None:
                return VerifierResult(status="fail-bucket",
                                      rationale=f"anchor not found in KG: {a.node_id}",
                                      ran_at_ts=time.time())
            anchor_claims.append(c)
        verdict = await self._llm_synthesis_judge(
            sentence_text=sentence.text,
            anchor_paraphrases=[c.paraphrase for c in anchor_claims],
            evidence_path=sentence.evidence_path or "",
        )
        status_str = verdict.get("status", "fail-entailment")
        check_str = verdict.get("synthesis_check", "unsupported")
        return VerifierResult(
            status=status_str if status_str in ("pass", "fail-entailment") else "fail-entailment",
            synthesis_check=check_str if check_str in ("pass", "trivial-restatement", "unsupported") else "unsupported",
            rationale=verdict.get("rationale", ""),
            ran_at_ts=time.time(),
        )

    async def _llm_synthesis_judge(self, *, sentence_text: str,
                                   anchor_paraphrases: list[str],
                                   evidence_path: str) -> dict:
        anchors_block = "\n".join(f"  - {p}" for p in anchor_paraphrases)
        prompt = (
            "Decide whether SENTENCE is a NON-TRIVIAL synthesis of the supporting ANCHORS.\n\n"
            f"SENTENCE: {sentence_text}\n\n"
            f"ANCHORS (paraphrased):\n{anchors_block}\n\n"
            f"AUTHOR-DECLARED EVIDENCE PATH: {evidence_path}\n\n"
            "Acceptable: sentence integrates multiple anchors into a statement not directly stated by any single anchor.\n"
            "Trivial restatement: sentence essentially repeats one anchor.\n"
            "Unsupported: sentence makes claims neither anchor supports.\n\n"
            "Reply ONLY with JSON: "
            '{"status": "pass" | "fail-entailment", '
            '"synthesis_check": "pass" | "trivial-restatement" | "unsupported", '
            '"rationale": "<one sentence>"}'
        )
        resp = await dispatch_agent(agent_type="claim-verifier", prompt=prompt, max_tokens=384)
        try:
            return json.loads(resp.content)
        except Exception:
            return {"status": "fail-entailment", "synthesis_check": "unsupported",
                    "rationale": "verifier output unparseable"}

    def _verify_speculate(self, sentence: SentenceBucket) -> VerifierResult:
        if not sentence.hedge_language:
            return VerifierResult(
                status="fail-bucket",
                rationale="speculate bucket requires hedge_language (e.g. 'we hypothesize that')",
                ran_at_ts=time.time(),
            )
        if sentence.authorization is None:
            return VerifierResult(
                status="pending-user-approval",
                rationale="speculation not pre-authorized; live AskUserQuestion gate required",
                ran_at_ts=time.time(),
            )
        # Authorization present + hedge present -> pass
        return VerifierResult(
            status="pass",
            rationale=f"speculation authorized via {sentence.authorization.source}",
            ran_at_ts=time.time(),
        )

    def _find_claim(self, node_id: str):
        if "." not in node_id:
            return None
        paper_id = node_id.split(".", 1)[0]
        paper = self.store.read_paper(paper_id)
        if paper is None:
            return None
        for c in paper.nodes.claims:
            if c.id == node_id:
                return c
        return None

    async def _llm_entailment(self, *, sentence_text: str, anchor_quote: str,
                              anchor_paraphrase: str) -> dict:
        prompt = (
            "Decide if SENTENCE faithfully paraphrases ANCHOR.\n\n"
            f"SENTENCE: {sentence_text}\n\n"
            f"ANCHOR (verbatim from source): \"{anchor_quote}\"\n"
            f"ANCHOR (paraphrase): {anchor_paraphrase}\n\n"
            "Acceptable: paraphrase preserves meaning, scope, polarity, and numerical values.\n"
            "Unacceptable: shifts polarity, scope, numerical values, or adds unsupported claims.\n\n"
            "Reply ONLY with JSON: "
            '{"status": "pass" | "fail-entailment", "score": <0.0-1.0>, "rationale": "<one sentence>"}'
        )
        resp = await dispatch_agent(agent_type="claim-verifier", prompt=prompt, max_tokens=256)
        try:
            return json.loads(resp.content)
        except Exception:
            return {"status": "fail-entailment", "score": 0.0, "rationale": "verifier output unparseable"}
