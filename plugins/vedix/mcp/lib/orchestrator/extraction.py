"""Two-tier extraction: fenced block → balanced-brace scan → cleanup → parse.
Per spec §4.4. Closes 'crude regex error classification' audit finding —
extract_python validates AST before returning, so syntax errors land in
Phase 3 not Phase 4.
"""
from __future__ import annotations
import ast
import json
import re
from typing import Optional


class ExtractionError(ValueError):
    pass


_JSON_FENCE = re.compile(r"```json\s*\n?(.*?)\n?```", re.DOTALL | re.IGNORECASE)
_LATEX_FENCE = re.compile(r"```latex\s*\n?(.*?)\n?```", re.DOTALL | re.IGNORECASE)
_PYTHON_FENCE = re.compile(r"```python\s*\n?(.*?)\n?```", re.DOTALL | re.IGNORECASE)
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _strip_control(s: str) -> str:
    return _CONTROL_CHARS.sub("", s)


def _balanced_brace_scan(text: str) -> Optional[str]:
    """Return the first balanced {...} block, ignoring braces in strings."""
    start = text.find("{")
    if start == -1:
        return None
    depth, in_str, escape = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def extract_json(text: str) -> dict:
    """Try ```json fence → balanced-brace scan → control-char strip → json.loads."""
    if not text or not text.strip():
        raise ExtractionError("empty input")
    # Tier 1: fenced
    m = _JSON_FENCE.search(text)
    candidate = m.group(1).strip() if m else None
    # Tier 2: balanced scan
    if candidate is None:
        candidate = _balanced_brace_scan(text)
    if candidate is None:
        raise ExtractionError(f"no JSON object found in input: {text[:200]!r}")
    candidate = _strip_control(candidate)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as e:
        raise ExtractionError(f"JSON parse failed: {e}; candidate={candidate[:200]!r}") from e


def extract_latex(text: str) -> str:
    m = _LATEX_FENCE.search(text)
    if m:
        return m.group(1).strip()
    # Fallback: assume the whole text is LaTeX
    if "\\begin{document}" in text or "\\documentclass" in text:
        return text.strip()
    raise ExtractionError("no LaTeX block found")


def extract_python(text: str) -> str:
    m = _PYTHON_FENCE.search(text)
    code = m.group(1).strip() if m else text.strip()
    try:
        ast.parse(code)
    except SyntaxError as e:
        raise ExtractionError(
            f"Python syntax error at line {e.lineno}: {e.msg}; offending code:\n{code[:500]}"
        ) from e
    return code
