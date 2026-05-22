"""Stage 3 — extract plain text from PDF/XML/HTML/text payloads.

Each extractor is a thin shim over a well-supported library:
  • PDF  → pdfminer.six
  • XML  → lxml (JATS-flavoured ``<body>`` paragraphs preferred)
  • HTML → BeautifulSoup
  • TXT  → passthrough
"""
from __future__ import annotations

from pathlib import Path


class UnsupportedFileFormat(Exception):
    """Raised when ``extract`` is given a file that doesn't match its
    declared extension (e.g. ``.pdf`` extension but RAR/ZIP magic, common
    when fetching from Anna's Archive which sometimes serves archives)."""


def _file_magic(p: Path, nbytes: int = 8) -> bytes:
    with p.open("rb") as f:
        return f.read(nbytes)


def _pdf_to_text(p: Path) -> str:
    """Extract text from a PDF using pdfminer.six (lazy-imported).

    Validates the PDF magic bytes first. If the file is actually a
    RAR/ZIP/other archive (Anna's Archive serves these for some titles),
    raises ``UnsupportedFileFormat`` so the caller can skip cleanly.
    """
    magic = _file_magic(p)
    if not magic.startswith(b"%PDF-"):
        raise UnsupportedFileFormat(
            f"{p.name}: expected PDF, got magic {magic[:8]!r} "
            f"(likely a RAR/ZIP/other archive served by the source)"
        )
    from pdfminer.high_level import extract_text  # type: ignore[import-untyped]

    return extract_text(str(p))


def _xml_to_text(p: Path) -> str:
    """Pull paragraphs from JATS-flavoured XML; fall back to all text."""
    from lxml import etree  # type: ignore[import-untyped]

    tree = etree.parse(str(p))
    body = tree.xpath("//body | //article-body")
    if body:
        chunks: list[str] = []
        for elem in body[0].iter("p"):
            chunks.append(" ".join(elem.itertext()).strip())
        return "\n\n".join(chunks)
    return " ".join(tree.getroot().itertext())


def _html_to_text(p: Path) -> str:
    """Extract human-readable text from HTML via BeautifulSoup."""
    from bs4 import BeautifulSoup

    raw = p.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(raw, "html.parser")
    return soup.get_text("\n")


def extract(src: Path, dest: Path) -> Path:
    """Extract text from ``src`` into ``dest`` and return ``dest``."""
    suffix = src.suffix.lower()
    if suffix == ".pdf":
        text = _pdf_to_text(src)
    elif suffix in (".xml", ".jats"):
        text = _xml_to_text(src)
    elif suffix in (".html", ".htm"):
        text = _html_to_text(src)
    else:
        text = src.read_text(encoding="utf-8", errors="ignore")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    return dest
