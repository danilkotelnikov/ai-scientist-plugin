#!/usr/bin/env python3
"""Scrape encyclopedic / popular-science chemistry text from Wikipedia.

Negative samples for the Layer B register classifier. The Wikipedia REST
+ MediaWiki extracts endpoints return plain text under the CC-BY-SA 4.0
license, which is the appropriate channel for ML training corpora that
need a non-academic register signal.

Output schema matches positives.jsonl / negatives.jsonl so the trainer
ingests both uniformly::

    {paper_id, para_idx, text, n_words, section, label, label_source}

Where ``label=0``, ``label_source="popsci_wikipedia"``, ``section`` is
the Wikipedia article subsection (or ``"Body"`` for the lead), and
``paper_id`` is ``wiki_<article-slug>``.

Volume target: ~3000-5000 paragraphs (~150 chemistry articles × ~20-30
substantive paragraphs each, post-filter).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path

import httpx


WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
USER_AGENT = (
    "vedix-corpus-build/3.0 (https://github.com/danilkotelnikov/vedix; "
    "mailto:OPENALEX_EMAIL) python-httpx"
)


# Canonical chemistry topics chosen to give broad register coverage:
# elements, compounds, reaction types, techniques, sub-fields,
# theoretical concepts, industrial processes. All Wikipedia article
# titles (mainspace, no namespace prefix).
CANONICAL_CHEMISTRY_TOPICS = [
    # Elements & periodic table
    "Periodic table", "Chemical element", "Atom", "Atomic nucleus",
    "Electron", "Hydrogen", "Helium", "Lithium", "Beryllium", "Boron",
    "Carbon", "Nitrogen", "Oxygen", "Fluorine", "Neon", "Sodium",
    "Magnesium", "Aluminium", "Silicon", "Phosphorus", "Sulfur",
    "Chlorine", "Argon", "Potassium", "Calcium", "Titanium", "Iron",
    "Cobalt", "Nickel", "Copper", "Zinc", "Bromine", "Iodine", "Mercury (element)",
    "Lead", "Uranium", "Plutonium",
    # Bonding & structure
    "Chemical bond", "Covalent bond", "Ionic bond", "Hydrogen bond",
    "Van der Waals force", "Metallic bonding", "Molecular orbital theory",
    "Lewis structure", "Hybridization (chemistry)", "VSEPR theory",
    "Stereochemistry", "Chirality (chemistry)", "Aromaticity",
    # Reactions & mechanisms
    "Chemical reaction", "Acid", "Base (chemistry)", "Acid-base reaction",
    "Oxidation", "Reduction (chemistry)", "Redox", "Catalysis",
    "Combustion", "Polymerization", "Esterification", "Hydrolysis",
    "Electrolysis", "Substitution reaction", "Addition reaction",
    "Elimination reaction",
    # Thermodynamics & kinetics
    "Chemical thermodynamics", "Chemical kinetics", "Enthalpy",
    "Entropy", "Gibbs free energy", "Activation energy", "Reaction rate",
    "Chemical equilibrium", "Le Chatelier's principle",
    # Sub-fields
    "Organic chemistry", "Inorganic chemistry", "Physical chemistry",
    "Analytical chemistry", "Biochemistry", "Polymer chemistry",
    "Medicinal chemistry", "Computational chemistry", "Green chemistry",
    "Photochemistry", "Electrochemistry", "Surface science",
    "Materials science",
    # Common compounds
    "Water", "Ammonia", "Methane", "Ethanol", "Acetone", "Benzene",
    "Glucose", "Sucrose", "Caffeine", "Aspirin", "Penicillin",
    "Hemoglobin", "Chlorophyll", "Sodium chloride", "Sulfuric acid",
    "Nitric acid", "Hydrochloric acid", "Sodium hydroxide",
    "Calcium carbonate", "Carbon dioxide", "Ozone",
    # Biomolecules
    "Protein", "Enzyme", "DNA", "RNA", "Lipid", "Carbohydrate",
    "Amino acid", "Nucleic acid",
    # Materials
    "Diamond", "Graphite", "Graphene", "Carbon nanotube",
    "Polymer", "Plastic", "Rubber", "Glass", "Ceramic", "Steel",
    "Concrete", "Silicone",
    # Techniques
    "Chromatography", "Gas chromatography", "Mass spectrometry",
    "Nuclear magnetic resonance spectroscopy",
    "Infrared spectroscopy", "X-ray crystallography",
    "Distillation", "Crystallization", "Filtration",
    "Titration", "Spectrophotometry", "Electrophoresis",
    # Industrial / applied
    "Haber process", "Contact process", "Bessemer process",
    "Cracking (chemistry)", "Petroleum refining",
    "Drug design", "Drug discovery", "Pharmaceutical industry",
    "Fertilizer", "Pesticide", "Plastic recycling",
    # Concepts
    "Mole (unit)", "Molar mass", "Avogadro constant",
    "Ideal gas law", "Stoichiometry", "Concentration",
    "Solution (chemistry)", "Phase (matter)", "Crystal structure",
    "Allotropy",
]


def _safe_paper_id(title: str) -> str:
    """Turn a Wikipedia title into a filesystem-safe slug."""
    s = re.sub(r"[^a-zA-Z0-9._-]", "_", title)
    return f"wiki_{s}"


async def fetch_wikipedia_extract(
    title: str, *, client: httpx.AsyncClient,
) -> tuple[str, str] | None:
    """Fetch one article's plain-text extract via the MediaWiki API.

    Returns ``(canonical_title, plain_text)`` on success, ``None`` on
    miss / disambiguation / failure. The ``extracts`` API returns the
    article body as plain text with sections separated by `\n\n` and
    headings stripped (we keep our own simple section tag).
    """
    params = {
        "action": "query",
        "format": "json",
        "titles": title,
        "prop": "extracts",
        "explaintext": "1",
        "exsectionformat": "plain",
        "redirects": "1",
    }
    try:
        r = await client.get(WIKIPEDIA_API, params=params, timeout=30)
        if r.status_code != 200:
            return None
        data = r.json()
    except Exception:  # noqa: BLE001
        return None

    pages = data.get("query", {}).get("pages") or {}
    for pid, page in pages.items():
        if pid == "-1":
            return None
        if "missing" in page or "extract" not in page:
            return None
        extract = page.get("extract", "")
        canonical = page.get("title", title)
        # Drop very short extracts (disambiguation / stub).
        if len(extract.strip()) < 600:
            return None
        # Drop disambiguation pages.
        if extract.strip().lower().startswith(
            ("may refer to", "is the name of", "can refer to")
        ):
            return None
        return canonical, extract
    return None


def segment_extract(text: str) -> list[tuple[str, str]]:
    """Split a Wikipedia plain-text extract into ``(section, paragraph)``.

    The ``exsectionformat=plain`` extract uses blank lines between
    paragraphs and a leading line of the form ``"== Section name =="``
    for section headers (in plain mode it shows as ``"== Name =="``).
    We strip Wikipedia "See also" / "References" / "External links" /
    "Further reading" sections wholesale — those are link lists with
    no real prose.
    """
    drop_sections = {
        "see also", "references", "external links", "further reading",
        "notes", "citations", "bibliography", "footnotes",
    }
    current_section = "Lead"
    out: list[tuple[str, str]] = []
    raw_paragraphs = re.split(r"\n\s*\n", text)
    for raw in raw_paragraphs:
        para = raw.strip()
        if not para:
            continue
        # Section header? "== Header ==" pattern in plain text.
        m = re.match(r"^=+\s*(.+?)\s*=+\s*$", para)
        if m:
            current_section = m.group(1).strip()
            continue
        if current_section.lower() in drop_sections:
            continue
        # Strip residual wiki markup that the extract endpoint sometimes
        # leaves in (rare): pipe-tables, file refs, citations.
        if para.startswith(("|", "{|", "File:", "[[Image:")):
            continue
        # Substantive paragraph guard: 60-1500 words.
        words = para.split()
        if len(words) < 60 or len(words) > 1500:
            continue
        out.append((current_section, para))
    return out


async def main_async(args, log) -> int:
    email = os.environ.get("OPENALEX_EMAIL", "research@example.com")
    ua = USER_AGENT.replace("OPENALEX_EMAIL", email)

    out_root = Path(os.path.expanduser(f"~/.vedix/corpus/{args.discipline}/en"))
    out_root.mkdir(parents=True, exist_ok=True)
    out_path = out_root / "popsci_negatives.jsonl"

    # Build the title list: canonical + (optionally) categorymembers.
    titles = list(CANONICAL_CHEMISTRY_TOPICS)
    if args.add_category_members:
        async with httpx.AsyncClient(
            timeout=30, headers={"User-Agent": ua}, follow_redirects=True,
        ) as client:
            for cat in args.add_category_members.split(","):
                cat = cat.strip()
                if not cat:
                    continue
                params = {
                    "action": "query", "format": "json", "list": "categorymembers",
                    "cmtitle": f"Category:{cat}", "cmlimit": "100", "cmtype": "page",
                }
                try:
                    r = await client.get(WIKIPEDIA_API, params=params)
                    members = r.json().get("query", {}).get("categorymembers", [])
                    new_titles = [
                        m["title"] for m in members
                        if m.get("ns") == 0 and ":" not in m.get("title", "")
                    ]
                    log.info("category %s -> %d new titles", cat, len(new_titles))
                    titles.extend(new_titles)
                except Exception as exc:  # noqa: BLE001
                    log.warning("category %s fetch failed: %s", cat, exc)

    # Dedup, cap to --target-articles
    seen: set[str] = set()
    unique_titles: list[str] = []
    for t in titles:
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        unique_titles.append(t)
    if args.target_articles:
        unique_titles = unique_titles[: args.target_articles]
    log.info("queued %d Wikipedia chemistry articles to fetch", len(unique_titles))

    # Fetch + segment.
    written_paragraphs = 0
    written_articles = 0
    skipped_articles = 0
    failed_articles = 0

    out_path.unlink(missing_ok=True)
    async with httpx.AsyncClient(
        timeout=30, headers={"User-Agent": ua}, follow_redirects=True,
    ) as client:
        with out_path.open("a", encoding="utf-8") as out_fh:
            for i, title in enumerate(unique_titles, start=1):
                result = await fetch_wikipedia_extract(title, client=client)
                if result is None:
                    failed_articles += 1
                    if i % 10 == 0:
                        log.info(
                            "[%d/%d] skip %r (no extract / disambiguation / too short)",
                            i, len(unique_titles), title,
                        )
                    await asyncio.sleep(0.4)
                    continue
                canonical, extract = result
                paras = segment_extract(extract)
                if not paras:
                    skipped_articles += 1
                    await asyncio.sleep(0.4)
                    continue
                paper_id = _safe_paper_id(canonical)
                for idx, (section, para) in enumerate(paras):
                    entry = {
                        "paper_id": paper_id,
                        "para_idx": idx,
                        "text": para,
                        "n_words": len(para.split()),
                        "section": section,
                        "label": 0,
                        "label_source": "popsci_wikipedia",
                    }
                    out_fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
                    written_paragraphs += 1
                written_articles += 1
                if i % 20 == 0 or i == len(unique_titles):
                    log.info(
                        "[%d/%d] %s -> %d paragraphs (running totals: "
                        "articles=%d paragraphs=%d skip=%d fail=%d)",
                        i, len(unique_titles), canonical, len(paras),
                        written_articles, written_paragraphs,
                        skipped_articles, failed_articles,
                    )
                # Polite delay so we don't hammer the API.
                await asyncio.sleep(0.4)

    print()
    print("Popsci Wikipedia scrape summary")
    print("-" * 50)
    print(f"  output:               {out_path}")
    print(f"  articles fetched:     {written_articles}")
    print(f"  articles skipped:     {skipped_articles + failed_articles}")
    print(f"  paragraphs written:   {written_paragraphs}")
    print()
    return 0


def main():
    import logging

    desc = (__doc__ or "").splitlines()[0] if __doc__ else "Popsci scraper"
    ap = argparse.ArgumentParser(description=desc)
    ap.add_argument("--discipline", default="chemistry",
                    choices=["chemistry", "biology", "physics", "medicine",
                             "computer_science", "materials", "geology"],
                    help="Discipline directory under ~/.vedix/corpus/")
    ap.add_argument("--target-articles", type=int, default=200,
                    help="Cap the number of Wikipedia articles to fetch.")
    ap.add_argument("--add-category-members", default="",
                    help="Comma-separated Wikipedia category names whose "
                         "direct page members get appended to the canonical "
                         "topic list. Example: "
                         "'Organic_compounds,Chemical_compounds_of_carbon'.")
    ap.add_argument("-v", "--verbose", action="count", default=0)
    args = ap.parse_args()

    level = logging.WARNING
    if args.verbose == 1:
        level = logging.INFO
    elif args.verbose >= 2:
        level = logging.DEBUG
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-5s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    log = logging.getLogger("vedix.popsci")
    sys.exit(asyncio.run(main_async(args, log)))


if __name__ == "__main__":
    main()
