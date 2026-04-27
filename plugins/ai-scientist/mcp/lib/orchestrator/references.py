"""Bidirectional citation validation. Per spec §4.12 and §8.3.

Per AI-Research-SKILLs citation-discipline (40% LLM citation error rate).
Closes 'uncited bibliography entries' (3 in 04a21066) audit finding.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional


_CITE_KEYS = re.compile(r"\\cite[a-z]*\{([^}]+)\}")
_BIB_ENTRY = re.compile(r"@\w+\s*\{\s*([^,\s]+)", re.MULTILINE)
_BIB_DOI = re.compile(r"doi\s*=\s*[{\"]?([^},\"\s]+)", re.IGNORECASE)


@dataclass
class CitationReport:
    cited_keys: set = field(default_factory=set)
    bib_keys: set = field(default_factory=set)
    dangling: list = field(default_factory=list)        # cited but not in .bib
    uncited: list = field(default_factory=list)          # in .bib but not cited
    crossref_failures: list = field(default_factory=list)
    hallucinated: list = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return not (self.dangling or self.uncited or self.crossref_failures or self.hallucinated)


def validate_citations(
    manuscript_tex: str,
    bib_path: Path,
    *,
    crossref_check: bool = True,
    crossref_client: Optional[Callable] = None,
    llm_judge: Optional[Callable] = None,
) -> CitationReport:
    bib_text = Path(bib_path).read_text(encoding="utf-8")
    cited_lists = [m.group(1) for m in _CITE_KEYS.finditer(manuscript_tex)]
    cited = set()
    for csv in cited_lists:
        for k in csv.split(","):
            k = k.strip()
            if k:
                cited.add(k)
    bib_keys = set(m.group(1) for m in _BIB_ENTRY.finditer(bib_text))
    report = CitationReport(cited_keys=cited, bib_keys=bib_keys)
    report.dangling = sorted(cited - bib_keys)
    report.uncited = sorted(bib_keys - cited)
    if crossref_check and crossref_client is not None:
        # Find DOIs per entry; verify each
        for entry_match in re.finditer(r"@\w+\s*\{\s*([^,\s]+)[^@]*", bib_text):
            key = entry_match.group(1)
            entry_text = entry_match.group(0)
            doi_match = _BIB_DOI.search(entry_text)
            if doi_match:
                doi = doi_match.group(1)
                try:
                    result = crossref_client(doi)
                    if not result.get("verified", False):
                        report.crossref_failures.append(key)
                except Exception:
                    report.crossref_failures.append(key)
    if llm_judge is not None:
        try:
            judgement = llm_judge(bib_text=bib_text, cited_keys=sorted(cited))
            report.hallucinated = list(judgement.get("hallucinated", []))
        except Exception:
            pass
    return report
