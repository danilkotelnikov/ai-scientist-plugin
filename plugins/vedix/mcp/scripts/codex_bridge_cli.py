#!/usr/bin/env python3
"""CLI wrapper for the Codex bridge — usable from Bash, hooks, and the
ai-scientist orchestrator's Phase F fallback.

Subcommands:
    task      <prompt>                       Submit a Codex task (waits, returns stdout)
    review    [--scope auto|...] [--base R]  Run /codex:review
    cross-validate                            Cross-validate Claude's output (stdin)
    fallback                                  Re-prompt a failed Claude task to Codex (stdin)
    annas     <query> [--max N]               Delegate Anna's Archive search to Codex
    detect-host                               Print 'claude_code'|'codex'|'gemini'|'unknown'
    failure-class                             Read stdin, print failure class or 'ok'

Examples:
    # Submit a Codex task
    python codex_bridge_cli.py task "Refactor utils.py for clarity" --timeout 300

    # Cross-validate a Claude output (read JSON spec from stdin)
    cat <<'EOF' | python codex_bridge_cli.py cross-validate
    {"task_type": "code", "claude_output": "...", "task_inputs": {...}}
    EOF

    # Re-prompt to Codex when Claude failed
    cat <<'EOF' | python codex_bridge_cli.py fallback
    {"original_prompt": "...", "failure_reason": "tos_refusal"}
    EOF

    # Detect failure class in arbitrary text
    echo "I cannot help with that request" | python codex_bridge_cli.py failure-class
    # -> tos_refusal

Exit codes:
    0   success / 'ok' / 'agree'
    1   minor_disagree / generic failure
    2   major_disagree / requires user decision
    3   codex_error (timed out, unavailable, etc.)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Add lib/ to path so we can import codex_bridge as a sibling package.
_THIS = Path(__file__).resolve()
sys.path.insert(0, str(_THIS.parent.parent / "lib"))

from codex_bridge import (
    CodexBridge,
    CodexUnavailable,
    CodexTimeout,
    detect_host,
)
from codex_bridge.bridge import looks_like_claude_failure


def _make_bridge(args: argparse.Namespace) -> CodexBridge:
    try:
        return CodexBridge(
            plugin_root=args.codex_plugin_root or os.environ.get("CODEX_PLUGIN_CC_ROOT"),
            default_model=args.model or "gpt-5.5",
            default_effort=args.effort or "xhigh",
            default_timeout_seconds=args.timeout or 600,
            require_claude_code=not args.allow_any_host,
        )
    except CodexUnavailable as e:
        print(f"CodexUnavailable: {e}", file=sys.stderr)
        sys.exit(3)


def cmd_task(args: argparse.Namespace) -> int:
    bridge = _make_bridge(args)
    try:
        r = bridge.task(
            args.prompt,
            model=args.model,
            effort=args.effort,
            write=args.write,
            wait=not args.background,
            timeout_seconds=args.timeout,
            resume=args.resume,
        )
    except CodexTimeout as e:
        print(f"CodexTimeout: {e}", file=sys.stderr)
        return 3
    print(r.stdout, end="")
    if r.stderr.strip():
        print(r.stderr, file=sys.stderr, end="")
    return 0 if r.is_ok() else 1


def cmd_review(args: argparse.Namespace) -> int:
    bridge = _make_bridge(args)
    try:
        if args.adversarial:
            r = bridge.adversarial_review(
                focus=args.focus or "",
                scope=args.scope,
                base=args.base,
                wait=not args.background,
                timeout_seconds=args.timeout,
            )
        else:
            r = bridge.review(
                scope=args.scope,
                base=args.base,
                wait=not args.background,
                timeout_seconds=args.timeout,
            )
    except CodexTimeout as e:
        print(f"CodexTimeout: {e}", file=sys.stderr)
        return 3
    print(r.stdout, end="")
    if r.stderr.strip():
        print(r.stderr, file=sys.stderr, end="")
    return 0 if r.is_ok() else 1


def cmd_cross_validate(args: argparse.Namespace) -> int:
    """Read JSON spec from stdin: {task_type, claude_output, task_inputs}."""
    spec = json.loads(sys.stdin.read())
    bridge = _make_bridge(args)
    cv = bridge.cross_validate(
        claude_output=spec["claude_output"],
        task_inputs=spec.get("task_inputs", {}),
        task_type=spec["task_type"],
        model=args.model,
        effort=args.effort or "high",
        timeout_seconds=args.timeout or 300,
    )
    print(json.dumps({
        "task_type": cv.task_type,
        "verdict": cv.codex_verdict,
        "confidence": cv.codex_confidence,
        "discrepancies": cv.discrepancies,
        "codex_alternative": cv.codex_alternative,
        "requires_user_decision": cv.requires_user_decision,
    }, indent=2))
    return {
        "agree": 0,
        "minor_disagree": 1,
        "major_disagree": 2,
        "codex_error": 3,
    }.get(cv.codex_verdict, 1)


def cmd_fallback(args: argparse.Namespace) -> int:
    """Read JSON from stdin: {original_prompt, failure_reason}."""
    spec = json.loads(sys.stdin.read())
    bridge = _make_bridge(args)
    try:
        r = bridge.re_prompt_on_failure(
            original_prompt=spec["original_prompt"],
            failure_reason=spec.get("failure_reason", "api_error"),
            model=args.model,
            effort=args.effort or "high",
            timeout_seconds=args.timeout or 600,
        )
    except CodexTimeout as e:
        print(f"CodexTimeout: {e}", file=sys.stderr)
        return 3
    print(r.stdout, end="")
    return 0 if r.is_ok() else 1


def cmd_annas(args: argparse.Namespace) -> int:
    bridge = _make_bridge(args)
    try:
        r = bridge.annas_search(
            args.query,
            max_results=args.max,
            timeout_seconds=args.timeout or 180,
        )
    except CodexTimeout as e:
        print(f"CodexTimeout: {e}", file=sys.stderr)
        return 3
    print(r.stdout, end="")
    return 0 if r.is_ok() else 1


def cmd_detect_host(_: argparse.Namespace) -> int:
    print(detect_host())
    return 0


def cmd_failure_class(_: argparse.Namespace) -> int:
    text = sys.stdin.read()
    cls = looks_like_claude_failure(text)
    print(cls or "ok")
    return 0 if cls is None else 1


# --- argparse setup ---------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(prog="codex_bridge_cli.py", description=__doc__)
    p.add_argument("--codex-plugin-root", default=None,
                   help="Path to codex-plugin-cc install (overrides env CODEX_PLUGIN_CC_ROOT)")
    p.add_argument("--model", default=None)
    p.add_argument("--effort", default=None, choices=["minimal", "low", "medium", "high", "xhigh"])
    p.add_argument("--timeout", type=int, default=None, help="Timeout in seconds")
    p.add_argument("--allow-any-host", action="store_true",
                   help="Skip the Claude Code-only guard (debug)")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("task")
    sp.add_argument("prompt")
    sp.add_argument("--write", action="store_true")
    sp.add_argument("--background", action="store_true")
    sp.add_argument("--resume", action="store_true")
    sp.set_defaults(func=cmd_task)

    sp = sub.add_parser("review")
    sp.add_argument("--scope", default="auto", choices=["auto", "working-tree", "branch"])
    sp.add_argument("--base", default=None)
    sp.add_argument("--background", action="store_true")
    sp.add_argument("--adversarial", action="store_true")
    sp.add_argument("--focus", default="")
    sp.set_defaults(func=cmd_review)

    sp = sub.add_parser("cross-validate")
    sp.set_defaults(func=cmd_cross_validate)

    sp = sub.add_parser("fallback")
    sp.set_defaults(func=cmd_fallback)

    sp = sub.add_parser("annas")
    sp.add_argument("query")
    sp.add_argument("--max", type=int, default=10)
    sp.set_defaults(func=cmd_annas)

    sp = sub.add_parser("detect-host")
    sp.set_defaults(func=cmd_detect_host)

    sp = sub.add_parser("failure-class")
    sp.set_defaults(func=cmd_failure_class)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
