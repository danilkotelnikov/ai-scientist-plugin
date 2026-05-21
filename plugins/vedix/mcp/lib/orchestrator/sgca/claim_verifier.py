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
        # Implemented in Task 10
        return VerifierResult(status="fail-bucket",
                              rationale="synthesize verification not yet implemented",
                              ran_at_ts=time.time())

    def _verify_speculate(self, sentence: SentenceBucket) -> VerifierResult:
        # Implemented in Task 11
        return VerifierResult(status="fail-bucket",
                              rationale="speculate verification not yet implemented",
                              ran_at_ts=time.time())

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
