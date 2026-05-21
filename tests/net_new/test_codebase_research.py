"""Tests for §5.5 codebase-aware research mode."""
from __future__ import annotations

from plugins.vedix.mcp.lib.orchestrator.codebase_research import CodebaseContext


def test_codebase_context_loads(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "model.py").write_text("def train(): pass\n", encoding="utf-8")
    (tmp_path / "src" / "data.py").write_text("def load(): pass\n", encoding="utf-8")
    ctx = CodebaseContext.from_path(tmp_path)
    files = ctx.list_files()
    assert "src/model.py" in files or "src\\model.py" in files
    funcs = ctx.list_functions()
    assert any(f["name"] == "train" for f in funcs)


def test_module_lookup(tmp_path):
    (tmp_path / "exp.py").write_text(
        "def run_experiment(seed=42):\n    return seed * 2\n", encoding="utf-8"
    )
    ctx = CodebaseContext.from_path(tmp_path)
    func = ctx.find_function("run_experiment")
    assert func is not None
    assert func["name"] == "run_experiment"
