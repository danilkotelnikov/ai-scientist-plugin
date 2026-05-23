#!/usr/bin/env python3
"""Bridge: lift scrape_nature.py output into the prepare_corpus.py layout.

``scrape_nature.py`` writes to
``~/.vedix/corpus/nature/<niche>/en/{pdf,text,acquisition.jsonl,downloaded.jsonl}``
because Nature is the source journal.

``prepare_corpus.py`` expects
``~/.vedix/corpus/<discipline>/<lang>/{pdf,text,acquisition.jsonl}``
because its layout is discipline-first (a single discipline corpus pools
papers from many journals).

This script symlinks (or copies, on Windows where symlinks need admin)
the Nature-acquired papers into the discipline-first layout so the
``segmentation`` → ``dedup`` → ``labeling`` → ``splits`` stages of
``prepare_corpus.py`` can run against them. It also drops the
``acquisition`` + ``download`` + ``extraction`` stage checkpoints so
those stages get skipped (we already did the work).

Run after every scrape_nature.py session, idempotent. Maps:

    nature/chemistry → chemistry
    nature/biology   → biology
    nature/medicine  → medicine
    nature/computer_science → computer_science
    nature/physics   → physics
    nature/earth     → geology       (prepare_corpus calls it geology)
    nature/materials → materials     (new — not in prepare_corpus's
                                       default DISCIPLINES list)
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path


NICHE_TO_DISCIPLINE: dict[str, str] = {
    "chemistry":        "chemistry",
    "biology":          "biology",
    "medicine":         "medicine",
    "computer_science": "computer_science",
    "physics":          "physics",
    "earth":            "geology",   # prepare_corpus calls this geology
    "materials":        "materials",  # not in DISCIPLINES — caller must
                                       # add to prepare_corpus.py if used
}

# prepare_corpus stages we skip (we did them in scrape_nature.py).
SKIPPED_STAGES = ("acquisition", "download", "extraction", "lang_verify")


def _home() -> Path:
    return Path(os.environ.get("USERPROFILE") or os.environ.get("HOME") or ".")


def _corpus_root() -> Path:
    return _home() / ".vedix" / "corpus"


def bridge_one_niche(niche: str, *, copy_mode: bool = False) -> tuple[int, str]:
    """Bridge one niche's nature-scrape output into the prepare_corpus layout.

    Returns ``(num_papers_bridged, target_dir_path)``.
    Returns ``(0, "")`` when the source dir is missing or empty.
    """
    if niche not in NICHE_TO_DISCIPLINE:
        raise ValueError(f"unknown niche {niche!r}; choose from {sorted(NICHE_TO_DISCIPLINE)}")
    discipline = NICHE_TO_DISCIPLINE[niche]

    src = _corpus_root() / "nature" / niche / "en"
    if not src.exists():
        return 0, ""

    dst = _corpus_root() / discipline / "en"
    dst.mkdir(parents=True, exist_ok=True)
    (dst / "pdf").mkdir(exist_ok=True)
    (dst / "text").mkdir(exist_ok=True)

    pdf_count = 0
    # Copy or symlink each PDF + text pair.
    for pdf in (src / "pdf").glob("*.pdf"):
        target = dst / "pdf" / pdf.name
        if target.exists():
            continue
        if copy_mode:
            shutil.copy2(pdf, target)
        else:
            try:
                os.symlink(pdf, target)
            except (OSError, NotImplementedError):
                # Fall back to copy when symlinks need admin (Windows
                # without Developer Mode enabled).
                shutil.copy2(pdf, target)
        pdf_count += 1

    for txt in (src / "text").glob("*.txt"):
        target = dst / "text" / txt.name
        if target.exists():
            continue
        if copy_mode:
            shutil.copy2(txt, target)
        else:
            try:
                os.symlink(txt, target)
            except (OSError, NotImplementedError):
                shutil.copy2(txt, target)

    # Merge the acquisition manifest. prepare_corpus uses this as the
    # paper list for the segmentation stage.
    src_acq = src / "downloaded.jsonl"
    if src_acq.exists():
        dst_acq = dst / "acquisition.jsonl"
        # Append (preserve any existing entries from a prior bridge).
        existing_dois: set[str] = set()
        if dst_acq.exists():
            for line in dst_acq.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    existing_dois.add(json.loads(line).get("doi", ""))
                except json.JSONDecodeError:
                    continue
        new_lines: list[str] = []
        for line in src_acq.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            doi = entry.get("doi", "")
            if doi and doi not in existing_dois:
                # Tag with the journal source so the bridge is auditable.
                entry["source_journal"] = "nature"
                new_lines.append(json.dumps(entry))
        if new_lines:
            with dst_acq.open("a", encoding="utf-8") as f:
                f.write("\n".join(new_lines) + "\n")

    # Drop stage-completion markers so prepare_corpus.py skips the
    # acquisition / download / extraction / lang_verify stages.
    ckpt_dir = dst / ".checkpoints"
    ckpt_dir.mkdir(exist_ok=True)
    for stage in SKIPPED_STAGES:
        (ckpt_dir / f"{stage}.done").write_text(
            json.dumps({
                "stage": stage,
                "skipped_by": "bridge_nature_to_corpus",
                "reason": "papers acquired via scrape_nature.py",
            }),
            encoding="utf-8",
        )

    return pdf_count, str(dst)


def main():
    ap = argparse.ArgumentParser(
        description="Bridge scrape_nature.py output into the prepare_corpus discipline layout."
    )
    ap.add_argument("--niche", choices=sorted(NICHE_TO_DISCIPLINE.keys()),
                    help="Bridge a single niche.")
    ap.add_argument("--all-niches", action="store_true",
                    help="Bridge every niche that has scrape output on disk.")
    ap.add_argument("--copy", action="store_true",
                    help="Copy files instead of symlinking. Use when Windows "
                         "Developer Mode is disabled (symlinks need admin).")
    args = ap.parse_args()

    if not (args.niche or args.all_niches):
        ap.error("specify --niche <NAME> or --all-niches")

    niches = sorted(NICHE_TO_DISCIPLINE.keys()) if args.all_niches else [args.niche]
    print()
    print("Bridging Nature scrape output into prepare_corpus layout")
    print("-" * 60)
    total_bridged = 0
    for niche in niches:
        count, target = bridge_one_niche(niche, copy_mode=args.copy)
        if count > 0:
            print(f"  {niche:<20} -> {target}: {count} papers")
            total_bridged += count
        else:
            print(f"  {niche:<20} -> (no scrape output; skipped)")
    print("-" * 60)
    print(f"  Total bridged: {total_bridged} papers")
    print()
    print("Next: prepare_corpus segmentation+ stages now run on the bridged data.")
    print("  python scripts/prepare_corpus.py --only-pair chemistry:en -v")
    print()


if __name__ == "__main__":
    sys.exit(main() or 0)
