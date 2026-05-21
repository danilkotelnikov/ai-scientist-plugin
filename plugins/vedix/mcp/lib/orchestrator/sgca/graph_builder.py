from __future__ import annotations
import asyncio
import time
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from pydantic import ValidationError
from ..dispatch import dispatch_agent
from .schema import KGFragment
from .kg_store import KGStore


class ExtractionFailure(Exception):
    ...


@dataclass
class _Failure:
    paper_id: str
    reason: str
    attempt: int


class GraphBuilder:
    def __init__(self, *, store: KGStore, concurrency: int = 8, max_retries: int = 1):
        self.store = store
        self.concurrency = concurrency
        self.max_retries = max_retries

    async def run(self, *, paper_list: list[dict]) -> dict:
        sem = asyncio.Semaphore(self.concurrency)
        failures: list[_Failure] = []
        extracted: list[str] = []

        async def _one(paper: dict):
            async with sem:
                try:
                    await self._extract_with_retries(paper)
                    extracted.append(paper["id"])
                except ExtractionFailure as e:
                    failures.append(_Failure(paper_id=paper["id"], reason=str(e),
                                             attempt=self.max_retries + 1))

        await asyncio.gather(*[_one(p) for p in paper_list])
        return {
            "extracted": len(extracted),
            "failed": len(failures),
            "failures": [{"paper_id": f.paper_id, "reason": f.reason} for f in failures],
        }

    async def _extract_with_retries(self, paper: dict) -> None:
        last_err = None
        for attempt in range(self.max_retries + 1):
            try:
                yaml_text = await self._call_extractor(paper, attempt=attempt)
                frag = self._parse_and_validate(yaml_text, paper)
                self._verify_quotes_against_raw(frag, raw_text_path=Path(paper["raw_text_path"]))
                self.store.write_paper(frag)
                return
            except (ValidationError, ExtractionFailure, yaml.YAMLError) as e:
                last_err = e
                continue
        raise ExtractionFailure(f"after {self.max_retries + 1} attempts: {last_err}")

    async def _call_extractor(self, paper: dict, *, attempt: int) -> str:
        raw_text = Path(paper["raw_text_path"]).read_text(encoding="utf-8")
        stricter_suffix = (
            "\n\nSCHEMA REMINDER: Output ONLY the YAML document. "
            "Every verbatim_quote MUST be a contiguous substring of the raw text. "
            "Every quote_byte_range MUST point to exact byte offsets."
        ) if attempt > 0 else ""
        prompt = (
            f"Extract a KG fragment from this paper.\n\n"
            f"Paper metadata:\n{paper.get('doi', '')} — {paper.get('title', '')}\n\n"
            f"Raw text:\n```\n{raw_text}\n```{stricter_suffix}"
        )
        resp = await dispatch_agent(agent_type="paper-extractor", prompt=prompt, max_tokens=8192)
        return resp.content

    def _parse_and_validate(self, yaml_text: str, paper: dict) -> KGFragment:
        try:
            data = yaml.safe_load(yaml_text)
        except yaml.YAMLError as e:
            raise ExtractionFailure(f"YAML parse error: {e}") from e
        if not isinstance(data, dict):
            raise ExtractionFailure(f"YAML did not parse to a mapping: {type(data).__name__}")
        # Inject extractor_ts if missing
        for claim in (data.get("nodes", {}).get("claims") or []):
            claim.setdefault("provenance", {}).setdefault("extractor_ts", time.time())
        return KGFragment.model_validate(data)

    def _verify_quotes_against_raw(self, frag: KGFragment, *, raw_text_path: Path) -> None:
        raw = raw_text_path.read_text(encoding="utf-8")
        for claim in frag.nodes.claims:
            s, e = claim.quote_byte_range
            actual = raw[s:e]
            if actual != claim.verbatim_quote:
                # Fallback: try substring search; if found, suggest correct range in the error
                idx = raw.find(claim.verbatim_quote)
                if idx == -1:
                    raise ExtractionFailure(
                        f"verbatim quote not found in raw for claim {claim.id}: "
                        f"expected {claim.verbatim_quote[:80]!r}"
                    )
                raise ExtractionFailure(
                    f"verbatim quote byte_range mismatch for {claim.id}: "
                    f"reported [{s},{e}] but actual offset is [{idx},{idx + len(claim.verbatim_quote)}]"
                )
