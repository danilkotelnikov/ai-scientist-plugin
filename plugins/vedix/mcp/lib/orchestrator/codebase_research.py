"""§5.5 Codebase-aware research mode.

When the operator points Vedix at an existing source tree (`vedix run
--codebase /path/to/repo`), we build a lightweight AST index of every
`.py` file so downstream agents can ground hypotheses / experiments in
the actual symbols that exist in the codebase. The index is
stdlib-only — no external deps, no embeddings — and is intentionally
cheap to rebuild between runs.

Future blocks may layer richer features (call graphs, type stubs) on
top of `CodebaseContext`, but the v3.0 contract is just files +
functions + classes.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CodebaseContext:
    """In-memory AST index of a Python source tree."""

    root: Path
    files: list[Path] = field(default_factory=list)
    _funcs: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_path(cls, root: Path | str) -> "CodebaseContext":
        """Build an index by recursively walking `root` for `*.py` files."""
        root_path = Path(root)
        files = list(root_path.rglob("*.py"))
        ctx = cls(root=root_path, files=files)
        ctx._index()
        return ctx

    def _index(self) -> None:
        """Populate `_funcs` with one entry per def / async def / class."""
        for f in self.files:
            try:
                tree = ast.parse(
                    f.read_text(encoding="utf-8", errors="ignore")
                )
            except SyntaxError:
                continue
            rel = str(f.relative_to(self.root))
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    self._funcs.append(
                        {
                            "file": rel,
                            "name": node.name,
                            "lineno": node.lineno,
                            "kind": "function",
                        }
                    )
                elif isinstance(node, ast.AsyncFunctionDef):
                    self._funcs.append(
                        {
                            "file": rel,
                            "name": node.name,
                            "lineno": node.lineno,
                            "kind": "async_function",
                        }
                    )
                elif isinstance(node, ast.ClassDef):
                    self._funcs.append(
                        {
                            "file": rel,
                            "name": node.name,
                            "lineno": node.lineno,
                            "kind": "class",
                        }
                    )

    def list_files(self) -> list[str]:
        """Return every indexed file as a path relative to `root`."""
        return [str(f.relative_to(self.root)) for f in self.files]

    def list_functions(self) -> list[dict[str, Any]]:
        """Return every indexed function / class entry."""
        return list(self._funcs)

    def find_function(self, name: str) -> dict[str, Any] | None:
        """Return the first indexed entry whose `name` matches."""
        for f in self._funcs:
            if f["name"] == name:
                return f
        return None
