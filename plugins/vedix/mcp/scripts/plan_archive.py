#!/usr/bin/env python3
"""Mine a plan/spec file into the plugin-development palace.

Called by the PostToolUse hook after Write to docs/{specs,plans}/*.md.
Per spec §7.5.
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser(prog="plan_archive.py")
    sub = p.add_subparsers(dest="cmd", required=True)
    mine = sub.add_parser("mine")
    mine.add_argument("--path", required=True)
    mine.add_argument("--palace", required=True)
    mine.add_argument("--wing", required=True)
    mine.add_argument("--room", required=True)
    mine.add_argument("--tags", default="")
    args = p.parse_args()
    if args.cmd != "mine":
        return 1
    path = Path(args.path)
    if not path.is_file():
        print(f"plan_archive: {path} not found", file=sys.stderr)
        return 1
    # The actual MCP call cannot happen from a shell-spawned process
    # (no MCP client). Instead, write a "queued mine" record that the
    # next interactive session can pick up. The pipeline will mine it
    # via MemPalace MCP at startup.
    queue_dir = Path(args.palace) / "_queue"
    queue_dir.mkdir(parents=True, exist_ok=True)
    queued = queue_dir / f"{path.stem}.txt"
    queued.write_text(
        f"path={path}\nwing={args.wing}\nroom={args.room}\ntags={args.tags}\n",
        encoding="utf-8",
    )
    print(f"plan_archive: queued mine for {path.name} -> {queued}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
