"""Vedix — Dataset preparation pipeline (§5.3.1).

Run for ALL pairs::

    python scripts/prepare_corpus.py \\
        --languages en,ru,es,de,fr,zh,ja \\
        --disciplines chemistry,biology,medicine,physics,mathematics,geology,computer_science,humanities \\
        --target-count 150

Run for ONE pair::

    python scripts/prepare_corpus.py --only-pair chemistry:en --target-count 150

Stages run idempotently with per-stage checkpoints under
``{corpus_root}/{discipline}/{lang}/.checkpoints/``. Re-running picks up
where the previous run left off; use ``--force-restart`` to scrub all
stage markers for the targeted pairs.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

# Make ``corpus_lib`` importable when this script is run directly.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from corpus_lib import (  # noqa: E402 — after sys.path tweak
    acquisition,
    download,
    extraction,
    lang_verify,
    segmentation,
    dedup,
    labeling,
    negative_generator,
    splits,
    stats,
)
from corpus_lib.checkpoint import StageCheckpoint  # noqa: E402

DISCIPLINES: list[str] = [
    "chemistry",
    "biology",
    "medicine",
    "physics",
    "mathematics",
    "geology",
    "computer_science",
    "humanities",
]
LANGUAGES: list[str] = ["en", "ru", "es", "de", "fr", "zh", "ja"]

_ALL_STAGES: tuple[str, ...] = (
    "acquisition",
    "download",
    "extraction",
    "lang_verify",
    "segmentation",
    "dedup",
    "labeling",
    "negatives",
    "splits",
    "stats",
)


def _home() -> Path:
    return Path(os.environ.get("USERPROFILE") or os.environ.get("HOME") or ".")


def _corpus_root() -> Path:
    return _home() / ".vedix" / "corpus"


def _pid(paper: dict) -> str:
    """Sanitise a paper's id/doi into a safe filename stem."""
    pid = paper.get("id") or paper.get("doi") or "x"
    return str(pid).replace("/", "_")


def _read_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l]


async def prepare_one_pair(
    *,
    discipline: str,
    language: str,
    target_count: int,
    corpus_root: Path | None = None,
    force_restart: bool = False,
    negatives_cap: int = 1000,
) -> None:
    """Run the 10-stage pipeline for one (discipline, language) pair."""
    root = (corpus_root or _corpus_root()) / discipline / language
    root.mkdir(parents=True, exist_ok=True)
    cp = StageCheckpoint(root=root)
    if force_restart:
        for stage in _ALL_STAGES:
            cp.reset(stage)

    print(
        f"\n=== preparing {discipline}/{language} (target {target_count} papers) ==="
    )

    # Stage 1 — acquisition
    if not cp.is_done("acquisition"):
        await acquisition.harvest(
            discipline=discipline,
            language=language,
            target_count=target_count,
            out_path=root / "acquisition.jsonl",
        )
        cp.mark_done("acquisition")
    candidates = _read_jsonl(root / "acquisition.jsonl")
    print(f"  [1/10] {len(candidates)} candidates")

    # Stage 2 — download
    if not cp.is_done("download"):
        pdf_dir = root / "pdf"
        urls_dests: list[tuple[str, Path]] = [
            (p["full_text_url"], pdf_dir / f"{_pid(p)}.pdf")
            for p in candidates
            if p.get("full_text_url")
        ]
        await download.download_many(urls_dests, concurrency=8)
        cp.mark_done("download", payload={"requested": len(urls_dests)})
    print("  [2/10] downloads complete")

    # Stage 3 — extraction
    if not cp.is_done("extraction"):
        text_dir = root / "text"
        n_ok = n_skipped = 0
        for p in candidates:
            pdf = root / "pdf" / f"{_pid(p)}.pdf"
            if not pdf.exists():
                continue
            try:
                extraction.extract(pdf, text_dir / f"{_pid(p)}.txt")
                n_ok += 1
            except extraction.UnsupportedFileFormat as exc:
                # Anna's Archive sometimes serves RAR/ZIP archives for the
                # md5 we requested. Skip gracefully so partial corpora still
                # work end-to-end.
                print(f"  [extract] skip {pdf.name}: {exc}")
                n_skipped += 1
            except Exception as exc:  # noqa: BLE001
                # Corrupted / encrypted / scanned-only PDFs land here.
                print(f"  [extract] skip {pdf.name} (extractor error): {exc}")
                n_skipped += 1
        cp.mark_done("extraction", payload={"extracted": n_ok, "skipped": n_skipped})
    print("  [3/10] text extracted")

    # Stage 4 — language verification
    if not cp.is_done("lang_verify"):
        kept = lang_verify.filter_papers(
            candidates, target_lang=language, text_root=root / "text"
        )
        (root / "lang_verified.jsonl").write_text(
            "\n".join(json.dumps(p) for p in kept) + ("\n" if kept else ""),
            encoding="utf-8",
        )
        cp.mark_done("lang_verify", payload={"kept": len(kept)})
    print("  [4/10] language verified")

    # Stage 5 — segmentation
    if not cp.is_done("segmentation"):
        kept = _read_jsonl(root / "lang_verified.jsonl")
        para_file = root / "paragraphs.jsonl"
        if para_file.exists():
            para_file.unlink()
        for p in kept:
            text_file = root / "text" / f"{_pid(p)}.txt"
            if text_file.exists():
                segmentation.segment_paper(
                    text_file,
                    paper_id=_pid(p),
                    language=language,
                    out_jsonl=para_file,
                )
        cp.mark_done("segmentation")
    print("  [5/10] segmented into paragraphs")

    # Stage 6 — dedup
    if not cp.is_done("dedup"):
        paras = _read_jsonl(root / "paragraphs.jsonl")
        kept = dedup.dedup_minhash(paras, jaccard_threshold=0.85)
        (root / "paragraphs_dedup.jsonl").write_text(
            "\n".join(json.dumps(p, ensure_ascii=False) for p in kept)
            + ("\n" if kept else ""),
            encoding="utf-8",
        )
        cp.mark_done("dedup", payload={"input": len(paras), "kept": len(kept)})
    print("  [6/10] deduplicated")

    # Stage 7 — labeling
    if not cp.is_done("labeling"):
        paras = _read_jsonl(root / "paragraphs_dedup.jsonl")
        positives = labeling.label_positives(paras)
        (root / "positives.jsonl").write_text(
            "\n".join(json.dumps(p, ensure_ascii=False) for p in positives)
            + ("\n" if positives else ""),
            encoding="utf-8",
        )
        cp.mark_done("labeling", payload={"positives": len(positives)})
    print("  [7/10] positives labeled")

    # Stage 8 — adversarial negatives
    if not cp.is_done("negatives"):
        positives = _read_jsonl(root / "positives.jsonl")
        # Cap to avoid runaway LLM cost on huge corpora.
        sample_positives = positives[:negatives_cap]
        negatives = await negative_generator.generate_negatives(
            sample_positives, concurrency=4
        )
        (root / "negatives.jsonl").write_text(
            "\n".join(json.dumps(n, ensure_ascii=False) for n in negatives)
            + ("\n" if negatives else ""),
            encoding="utf-8",
        )
        cp.mark_done("negatives", payload={"generated": len(negatives)})
    print("  [8/10] adversarial negatives generated")

    # Stage 9 — splits
    if not cp.is_done("splits"):
        pos = _read_jsonl(root / "positives.jsonl")
        neg = _read_jsonl(root / "negatives.jsonl")
        combined = pos + neg
        train, val, test = splits.stratified_split_by_paper(
            combined, val_frac=0.1, test_frac=0.1, seed=42
        )
        for name, lst in (("train", train), ("val", val), ("test", test)):
            (root / f"{name}.jsonl").write_text(
                "\n".join(json.dumps(d, ensure_ascii=False) for d in lst)
                + ("\n" if lst else ""),
                encoding="utf-8",
            )
        cp.mark_done(
            "splits",
            payload={
                "train": len(train),
                "val": len(val),
                "test": len(test),
            },
        )
    print("  [9/10] train/val/test split")

    # Stage 10 — stats
    if not cp.is_done("stats"):
        train = _read_jsonl(root / "train.jsonl")
        val = _read_jsonl(root / "val.jsonl")
        test = _read_jsonl(root / "test.jsonl")
        stats.compute_stats(
            train=train, val=val, test=test, out=root / "corpus_stats.json"
        )
        cp.mark_done("stats")
    print(f"  [10/10] stats written. Pair {discipline}/{language} READY.")


async def main_async(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--languages", default=",".join(LANGUAGES))
    ap.add_argument("--disciplines", default=",".join(DISCIPLINES))
    ap.add_argument("--target-count", type=int, default=150)
    ap.add_argument("--only-pair", default=None, help="discipline:language")
    ap.add_argument("--corpus-root", default=None, type=Path)
    ap.add_argument("--force-restart", action="store_true")
    ap.add_argument("--negatives-cap", type=int, default=1000)
    ap.add_argument(
        "-v", "--verbose",
        action="count",
        default=0,
        help="Increase log verbosity (-v INFO, -vv DEBUG).",
    )
    args = ap.parse_args(argv)

    # Configure logging based on --verbose count.
    import logging
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

    corpus_root = args.corpus_root  # defaults to _corpus_root() in prepare_one_pair

    if args.only_pair:
        d, l = args.only_pair.split(":", 1)
        await prepare_one_pair(
            discipline=d,
            language=l,
            target_count=args.target_count,
            corpus_root=corpus_root,
            force_restart=args.force_restart,
            negatives_cap=args.negatives_cap,
        )
        return 0

    for d in args.disciplines.split(","):
        for l in args.languages.split(","):
            try:
                await prepare_one_pair(
                    discipline=d.strip(),
                    language=l.strip(),
                    target_count=args.target_count,
                    corpus_root=corpus_root,
                    force_restart=args.force_restart,
                    negatives_cap=args.negatives_cap,
                )
            except Exception as e:  # pragma: no cover - top-level dispatcher
                print(f"[prepare_corpus] {d}/{l} FAILED: {e}")
                continue
    return 0


def main() -> None:  # pragma: no cover - thin shell
    sys.exit(asyncio.run(main_async()))


if __name__ == "__main__":  # pragma: no cover
    main()
