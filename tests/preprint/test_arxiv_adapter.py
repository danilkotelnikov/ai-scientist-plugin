"""§5.9 Task 3 — arXiv preprint adapter."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from plugins.vedix.mcp.lib.orchestrator.preprint.arxiv_adapter import (
    ARXIV_SUBMIT_URL,
    submit_to_arxiv,
)


def _write_pdf(tmp_path: Path) -> Path:
    pdf = tmp_path / "manuscript.pdf"
    pdf.write_bytes(b"%PDF-1.4\nfake-pdf-body\n%%EOF\n")
    return pdf


def _write_token(tmp_path: Path) -> Path:
    token = tmp_path / "arxiv.token"
    token.write_text("dummy-token", encoding="utf-8")
    return token


def test_dry_run_returns_preview(tmp_path: Path) -> None:
    pdf = _write_pdf(tmp_path)
    md = {
        "title": "Title",
        "abstract": "Abstract",
        "authors": ["A. Person"],
        "categories": ["cs.LG"],
    }
    result = submit_to_arxiv(
        manuscript_pdf=pdf,
        metadata=md,
        credentials_path=tmp_path / "arxiv.token",
        dry_run=True,
    )
    assert result["status"] == "dry-run"
    assert result["target"] == "arxiv"
    assert result["would_submit_pdf"] == str(pdf)
    assert result["submit_url"] == ARXIV_SUBMIT_URL
    assert result["metadata"]["categories"] == ["cs.LG"]


def test_missing_token_returns_error(tmp_path: Path) -> None:
    pdf = _write_pdf(tmp_path)
    result = submit_to_arxiv(
        manuscript_pdf=pdf,
        metadata={"title": "T"},
        credentials_path=tmp_path / "absent.token",
        dry_run=False,
    )
    assert result["status"] == "error"
    assert "token" in result["reason"].lower()


def test_missing_pdf_returns_error(tmp_path: Path) -> None:
    token = _write_token(tmp_path)
    result = submit_to_arxiv(
        manuscript_pdf=tmp_path / "ghost.pdf",
        metadata={"title": "T"},
        credentials_path=token,
        dry_run=False,
    )
    assert result["status"] == "error"
    assert "pdf" in result["reason"].lower()


def test_success_returns_submission_id(tmp_path: Path) -> None:
    pdf = _write_pdf(tmp_path)
    token = _write_token(tmp_path)
    md = {
        "title": "Test paper",
        "abstract": "Body",
        "authors": ["A B", "C D"],
        "categories": ["cs.LG", "stat.ML"],
    }
    fake_resp = MagicMock(
        status_code=201,
        text="ok",
    )
    fake_resp.json = lambda: {"submission_id": "arXiv:2401.00001"}
    with patch("httpx.Client.post", return_value=fake_resp) as p:
        result = submit_to_arxiv(
            manuscript_pdf=pdf,
            metadata=md,
            credentials_path=token,
            dry_run=False,
        )
        assert p.called
        args, kwargs = p.call_args
        # called with the submit URL + Bearer header
        assert args[0] == ARXIV_SUBMIT_URL
        assert kwargs["headers"]["Authorization"] == "Bearer dummy-token"
        # title + authors + categories are flattened to strings
        assert kwargs["data"]["title"] == "Test paper"
        assert kwargs["data"]["authors"] == "A B; C D"
        assert kwargs["data"]["categories"] == "cs.LG,stat.ML"
        assert "manuscript" in kwargs["files"]
    assert result["status"] == "ok"
    assert result["target"] == "arxiv"
    assert result["submission_id"] == "arXiv:2401.00001"
    assert result["http_status"] == 201


def test_failure_returns_error_with_body(tmp_path: Path) -> None:
    pdf = _write_pdf(tmp_path)
    token = _write_token(tmp_path)
    fake_resp = MagicMock(status_code=400, text="malformed metadata")
    fake_resp.json = lambda: {"error": "malformed metadata"}
    with patch("httpx.Client.post", return_value=fake_resp):
        result = submit_to_arxiv(
            manuscript_pdf=pdf,
            metadata={"title": "T"},
            credentials_path=token,
            dry_run=False,
        )
    assert result["status"] == "error"
    assert result["target"] == "arxiv"
    assert result["http_status"] == 400
    assert "malformed" in result["body"].lower()


def test_custom_submit_url_honoured(tmp_path: Path) -> None:
    pdf = _write_pdf(tmp_path)
    md = {"title": "T", "abstract": "A", "authors": [], "categories": []}
    result = submit_to_arxiv(
        manuscript_pdf=pdf,
        metadata=md,
        credentials_path=tmp_path / "arxiv.token",
        dry_run=True,
        submit_url="https://staging.arxiv.org/sword/",
    )
    assert result["submit_url"] == "https://staging.arxiv.org/sword/"


def test_success_with_non_json_response(tmp_path: Path) -> None:
    """Servers that return text/plain still resolve to ``ok``."""
    pdf = _write_pdf(tmp_path)
    token = _write_token(tmp_path)
    fake_resp = MagicMock(status_code=200, text="received")

    def _raise():
        raise ValueError("not JSON")

    fake_resp.json = _raise
    with patch("httpx.Client.post", return_value=fake_resp):
        result = submit_to_arxiv(
            manuscript_pdf=pdf,
            metadata={"title": "T"},
            credentials_path=token,
            dry_run=False,
        )
    assert result["status"] == "ok"
    assert result["http_status"] == 200
    assert result["response"] == {"raw": "received"}
