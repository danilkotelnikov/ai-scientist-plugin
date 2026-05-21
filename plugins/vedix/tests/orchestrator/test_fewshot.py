from pathlib import Path
import pytest
from mcp.lib.orchestrator.fewshot import FewShotInjector


def test_inject_wraps_examples_in_xml_blocks(tmp_path):
    ex1 = tmp_path / "ex1.txt"
    ex1.write_text("Example 1 body.")
    inj = FewShotInjector()
    out = inj.inject("Original prompt.", [ex1])
    assert "<example" in out
    assert "Example 1 body." in out
    assert "</example>" in out
    assert "Original prompt." in out


def test_inject_preserves_order(tmp_path):
    ex1 = tmp_path / "a.txt"; ex1.write_text("AAA")
    ex2 = tmp_path / "b.txt"; ex2.write_text("BBB")
    inj = FewShotInjector()
    out = inj.inject("end", [ex1, ex2])
    assert out.index("AAA") < out.index("BBB") < out.index("end")


def test_inject_skips_missing_files(tmp_path):
    real = tmp_path / "real.txt"; real.write_text("real")
    fake = tmp_path / "missing.txt"
    inj = FewShotInjector()
    out = inj.inject("X", [real, fake])
    assert "real" in out
    # Missing file silently skipped


def test_inject_handles_json_examples(tmp_path):
    ex = tmp_path / "review.json"
    ex.write_text('{"Overall": 6, "Decision": "Accept"}')
    inj = FewShotInjector()
    out = inj.inject("X", [ex])
    assert '"Overall": 6' in out
