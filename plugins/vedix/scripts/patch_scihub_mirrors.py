#!/usr/bin/env python3
"""Patch the cloned Sci-Hub-MCP-Server to use a live mirror list.

The upstream ``scihub`` PyPI package ships an ``AVAILABLE_SCIHUB_BASE_URL``
constant whose entries (sci-hub.tw, sci-hub.is, sci-hub.mn, ...) have all
been dead for years. Every ``fetch(doi)`` call burns the retry budget on
unreachable hosts and reports ``status: not_found``.

This patcher edits the cloned ``sci_hub_search.py`` to override the
SciHub instance's ``available_base_url_list`` after construction with a
runtime-configurable list (env var ``SCIHUB_BASE_URLS``, comma-separated,
defaulting to the current verified-live mirrors).

Idempotent: re-running detects the patch marker and exits cleanly.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

PATCH_MARKER = "# vedix-mirror-override v1"

DEFAULT_LIVE_MIRRORS = [
    "sci-hub.ru",
    "sci-hub.se",
    "sci-hub.st",
    "sci-hub.cat",
    "www.tesble.com",
]


PATCH_BLOCK = f'''{PATCH_MARKER}
# Override the upstream scihub package's dead mirror list. Read from the
# SCIHUB_BASE_URLS env var (comma-separated) or fall back to a curated
# list of currently-reachable mirrors. Reapply on every create.
_VEDIX_DEFAULT_MIRRORS = {DEFAULT_LIVE_MIRRORS!r}


def _vedix_live_mirrors():
    raw = os.environ.get("SCIHUB_BASE_URLS", "")
    if raw.strip():
        return [m.strip() for m in raw.split(",") if m.strip()]
    return list(_VEDIX_DEFAULT_MIRRORS)


_vedix_original_create = create_scihub_instance


def create_scihub_instance():
    sh = _vedix_original_create()
    sh.available_base_url_list = _vedix_live_mirrors()
    sh.current_base_url_index = 0
    return sh
'''


def patch_file(path: Path) -> bool:
    """Apply the mirror-override patch to ``path``. Returns True if changed."""
    if not path.exists():
        print(f"ERROR: {path} not found. Run install.sh/install.ps1 to clone first.", file=sys.stderr)
        return False

    text = path.read_text(encoding="utf-8")
    if PATCH_MARKER in text:
        print(f"  already patched: {path}")
        return False

    # Append the patch block to the end of the file. By redefining
    # create_scihub_instance after the original, Python's module-import
    # behavior means our override wins.
    patched = text.rstrip() + "\n\n\n" + PATCH_BLOCK + "\n"
    path.write_text(patched, encoding="utf-8")
    print(f"  patched: {path}")
    return True


def main() -> int:
    vedix_home = Path(os.environ.get(
        "VEDIX_HOME",
        os.environ.get("AI_SCIENTIST_HOME", str(Path.home() / ".vedix")),
    ))
    target = vedix_home / "external" / "Sci-Hub-MCP-Server" / "sci_hub_search.py"
    print(f"Patching Sci-Hub MCP mirror list at {target}")
    changed = patch_file(target)
    print("Done." if changed else "No change needed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
