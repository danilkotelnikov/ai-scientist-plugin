# tests/orchestrator/test_extraction.py
import pytest
from mcp.lib.orchestrator.extraction import extract_json, extract_latex, extract_python, ExtractionError


def test_extract_json_clean():
    text = '{"k": "v"}'
    assert extract_json(text) == {"k": "v"}


def test_extract_json_fenced():
    text = '```json\n{"k": 1}\n```'
    assert extract_json(text) == {"k": 1}


def test_extract_json_with_prose_around():
    text = 'Here is the result:\n```json\n{"k": [1,2,3]}\n```\nDone.'
    assert extract_json(text) == {"k": [1, 2, 3]}


def test_extract_json_unfenced_with_prose():
    text = 'Here you go: {"a": "b"} cheers'
    assert extract_json(text) == {"a": "b"}


def test_extract_json_nested():
    text = '{"a": {"b": {"c": 1}}}'
    assert extract_json(text) == {"a": {"b": {"c": 1}}}


def test_extract_json_strips_control_chars():
    text = '{"a": "\x00\x01b"}'  # NUL + SOH
    result = extract_json(text)
    assert result["a"] == "b"


def test_extract_json_braces_in_strings_are_ignored():
    text = '{"k": "value with { brace"}'
    assert extract_json(text) == {"k": "value with { brace"}


def test_extract_json_malformed_raises():
    text = "not json at all"
    with pytest.raises(ExtractionError):
        extract_json(text)


def test_extract_latex_fenced():
    text = '```latex\n\\begin{document}hi\\end{document}\n```'
    assert extract_latex(text) == "\\begin{document}hi\\end{document}"


def test_extract_python_validates_ast():
    text = '```python\ndef f():\n    return 1\n```'
    assert extract_python(text) == "def f():\n    return 1"


def test_extract_python_raises_on_syntax_error():
    text = '```python\ndef f(:\n    return 1\n```'  # malformed
    with pytest.raises(ExtractionError, match="syntax"):
        extract_python(text)
