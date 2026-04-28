"""Anti-LLMish lint — empirically-grounded blacklist + style metrics.

Closes review-doc + spec §6.1. Sources: Liang et al. 2024 (PubMed 15M
abstracts), ICLR 2024 peer-review excess-vocabulary study.
"""
from __future__ import annotations
import re
from typing import Optional

# Tier 1 — measured ≥9× excess in post-ChatGPT corpora; block on first hit.
TIER1_BLACKLIST = [
    "delve", "delves", "delving", "delved",
    "underscore", "underscores", "underscoring", "underscored",
    "intricate", "intricacies", "intricately",
    "showcase", "showcases", "showcasing", "showcased",
    "meticulous", "meticulously",
    "commendable",
]

# Tier 2 — strong signal across editorial sources; warn on ≥2 in a section.
TIER2_BLACKLIST = [
    "robust", "landscape", "vibrant", "tapestry", "testament",
    "leverages", "leverage", "harness", "harnesses", "harnessing",
    "foster", "fosters", "fostering",
    "navigate", "navigates", "embark", "embarks",
    "paradigm", "paradigms", "multifaceted", "nuanced",
    "transformative", "revolutionary", "comprehensive", "holistic",
    "seamless", "seamlessly", "bustling",
    "treasure trove", "wealth of", "plethora", "myriad",
    "unveil", "unveils", "unveiling", "unleash", "unleashes",
    "cutting-edge", "state-of-the-art", "unprecedented",
    "groundbreaking", "renowned", "boasts", "boast",
    "innovative", "garner", "garners", "enduring", "interplay",
    "aligns with", "align with",
    "highlighting", "emphasizing", "bolstered",
    "enhance", "enhances", "enhanced",
    "pivotal", "realm", "crucial",
]

# Tier 3 — phrase regexes; block on match.
TIER3_PHRASE_PATTERNS = [
    r"it is important to note( that)?",
    r"it should be noted( that)?",
    r"it is worth mentioning",
    r"in conclusion,",
    r"\bultimately,",
    r"while it is true that",
    r"in the realm of",
    r"in the world of",
    r"in the era of",
    r"plays?\s+an?\s+(crucial|pivotal|key)\s+role",
    r"^(Furthermore|Moreover|Additionally|Notably|Importantly|Interestingly|Remarkably|Fascinatingly),",
    r"^(Certainly|Absolutely|Of course),",
    r"studies have shown",
    r"research indicates",
    r"experts agree",
    r"it is widely accepted",
    r"it is well established",
]

# Disciplinary exemptions: tier-2 word + this regex anywhere = ignore that hit.
EXEMPTIONS = {
    "robust": [r"\brobust regression\b", r"\brobust stability\b",
               r"\brobust standard error", r"\brobust optimization\b"],
    "comprehensive": [r"\bcomprehensive search (strategy|protocol)\b",
                      r"\bsystematic review\b"],
    "novel": [r"\bsee Appendix\b", r"\bsearch protocol\b",
              r"\bto our knowledge\b"],
    "crucial": [r"crucial (Ser|Thr|Tyr|Lys)\d+",  # phosphorylation site
                r"crucial phosphorylation"],
}


def _split_paragraphs(text: str) -> list:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def lint_text(text: str) -> dict:
    """Returns dict with hits[] and style metrics."""
    hits = []
    paragraphs = _split_paragraphs(text)
    sections = [text]  # treated as one section unless caller pre-splits

    # Tier 1 — first hit blocks
    for term in TIER1_BLACKLIST:
        pattern = re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)
        for m in pattern.finditer(text):
            # Check exemption
            if any(re.search(p, text, re.IGNORECASE)
                   for p in EXEMPTIONS.get(term, [])):
                continue
            hits.append({
                "tier": 1, "term": term, "start": m.start(), "end": m.end(),
                "match": m.group(0),
                "rationale": "Empirically excessive in post-ChatGPT corpora (Liang et al. 2024).",
            })

    # Tier 2 — count per section; flag if ≥2
    for section in sections:
        per_term_count = {}
        per_term_matches = {}
        for term in TIER2_BLACKLIST:
            if term in EXEMPTIONS:
                # Skip if exempted in context
                if any(re.search(p, section, re.IGNORECASE)
                       for p in EXEMPTIONS[term]):
                    continue
            pattern = re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)
            ms = list(pattern.finditer(section))
            if ms:
                per_term_count[term] = len(ms)
                per_term_matches[term] = ms
        for term, cnt in per_term_count.items():
            if cnt >= 2:
                for m in per_term_matches[term]:
                    hits.append({
                        "tier": 2, "term": term, "start": m.start(),
                        "end": m.end(), "match": m.group(0),
                        "rationale": f"Tier-2 LLM-style word; {cnt} occurrences in section (≥2 threshold).",
                    })

    # Tier 3 — phrase regex
    for pat in TIER3_PHRASE_PATTERNS:
        rx = re.compile(pat, re.IGNORECASE | re.MULTILINE)
        for m in rx.finditer(text):
            hits.append({
                "tier": 3, "term": pat, "start": m.start(), "end": m.end(),
                "match": m.group(0),
                "rationale": "Tier-3 phrase pattern (filler / sycophantic / authority surrogate).",
            })

    return {"hits": hits, "paragraph_count": len(paragraphs)}


EM_DASH_THRESHOLD_WARN = 2.0  # per 1000 words
EM_DASH_THRESHOLD_BLOCK = 5.0


def _word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text))


def _em_dash_metrics(text: str) -> Optional[dict]:
    n = text.count("—") + text.count("–")
    wc = _word_count(text) or 1
    rate = (n / wc) * 1000.0
    if rate < EM_DASH_THRESHOLD_WARN:
        return None
    return {
        "tier": 4, "metric": "em_dash_density",
        "value": round(rate, 2), "occurrences": n,
        "rationale": (f"{rate:.1f} em-dashes per 1000 words "
                      f"(human ≤ 2; GPT-4.1 ≈ 10.6, Claude Opus ≈ 9.1)."),
    }


_EVAL_ADJ = re.compile(
    r"\b(robust|scalable|efficient|comprehensive|seamless|innovative|"
    r"holistic|elegant|powerful|flexible|extensible)\b",
    re.IGNORECASE,
)
_TRICOLON = re.compile(
    r"\b(\w+),\s*(\w+),?\s+and\s+(\w+)\b",
)


def _tricolon_metric(text: str) -> list:
    out = []
    for m in _TRICOLON.finditer(text):
        words = [m.group(1), m.group(2), m.group(3)]
        if all(_EVAL_ADJ.match(w) for w in words):
            out.append({
                "tier": 4, "metric": "evaluative_tricolon",
                "match": m.group(0),
                "start": m.start(), "end": m.end(),
                "rationale": "Three evaluative adjectives in a row simulate "
                             "comprehensiveness; each must have a metric.",
            })
    return out


_PARTICIPIAL = re.compile(
    r",\s*(highlighting|underscoring|demonstrating|emphasizing|"
    r"showcasing|illustrating)\s+[^.]+\.",
    re.IGNORECASE,
)


def _participial_metric(text: str) -> list:
    out = []
    for m in _PARTICIPIAL.finditer(text):
        out.append({
            "tier": 4, "metric": "participial_commentary",
            "match": m.group(0)[:80],
            "start": m.start(), "end": m.end(),
            "rationale": "Participial commentary attaches editorial weight without analysis.",
        })
    return out


def _augment_with_style(out: dict, text: str) -> dict:
    em = _em_dash_metrics(text)
    if em:
        out["hits"].append(em)
    out["hits"].extend(_tricolon_metric(text))
    out["hits"].extend(_participial_metric(text))
    return out


# Override the original lint_text to chain style metrics.
_original_lint_text = lint_text


def lint_text(text: str) -> dict:  # type: ignore[no-redef]
    out = _original_lint_text(text)
    return _augment_with_style(out, text)


# --- Claim audit (intra-phase ideation re-dispatch triggers) ---

NUMBER_RX = (
    r"(p\s*[<=>]\s*0\.\d+|p\s*=\s*\d+|n\s*=\s*\d+|"
    r"\d+(\.\d+)?\s*(%|ms|s|GB|MB|x|\xd7|seconds|minutes|hours)|"
    r"\b\d+\.\d+|"
    r"(95|99)%\s*CI|F\(\d+|t\(\d+|χ²)"
)


def _has_quantification(window: str) -> bool:
    return bool(re.search(NUMBER_RX, window, re.IGNORECASE))


def _has_prior_work_survey(window: str) -> bool:
    return bool(re.search(
        r"(see Appendix|search protocol|to our knowledge|prior work)",
        window, re.IGNORECASE))


def _has_complexity(window: str) -> bool:
    return bool(re.search(r"\bO\([^)]+\)|complexity|sub-?(linear|quadratic)",
                          window, re.IGNORECASE))


def _has_robustness_eval(window: str) -> bool:
    return bool(re.search(
        r"(adversarial|distribution[-\s]shift|noise model|SNR|perturbation)",
        window, re.IGNORECASE))


def _has_held_out_eval(window: str) -> bool:
    return bool(re.search(
        r"(held[-\s]out|out[-\s]of[-\s]distribution|OOD|test set|cross[-\s]validation)",
        window, re.IGNORECASE))


def _has_test_statistic(window: str) -> bool:
    return bool(re.search(
        r"(p\s*[<=]|F\(\d+|t\(\d+|χ²|chi[-\s]square|ANOVA|Mann[-\s]Whitney)",
        window, re.IGNORECASE))


CLAIM_PATTERNS = [
    ("outperforms", r"\b(outperforms?|better than|improves?|superior)\b",
     lambda w: not _has_quantification(w)),
    ("novel", r"\b(novel|first to|unprecedented)\b",
     lambda w: not _has_prior_work_survey(w)),
    ("scalable", r"\bscalable\b",
     lambda w: not _has_complexity(w)),
    ("efficient", r"\b(efficient|computationally efficient)\b",
     lambda w: not _has_quantification(w)),
    ("robust", r"\brobust to\b",
     lambda w: not _has_robustness_eval(w)),
    ("generalizes", r"\bgeneralizes?\b",
     lambda w: not _has_held_out_eval(w)),
    ("significant", r"\bsignificant(ly)?\b",
     lambda w: not _has_test_statistic(w)),
]

WINDOW_CHARS = 200


def audit_claims(text: str) -> dict:
    """Scans for unquantified-claim patterns and emits clarification requests."""
    requests = []
    for label, pattern, gate in CLAIM_PATTERNS:
        rx = re.compile(pattern, re.IGNORECASE)
        for m in rx.finditer(text):
            window = text[max(0, m.start() - WINDOW_CHARS):
                          m.end() + WINDOW_CHARS]
            if gate(window):
                requests.append({
                    "pattern": label,
                    "match": m.group(0),
                    "start": m.start(),
                    "end": m.end(),
                    "window_excerpt": window[:300],
                })
    return {"clarification_requests": requests}
