"""Block 11 Task 5 — preprint_submit dispatcher routing.

Confirms that the CLI hook (``orchestrator.hooks.preprint_submit``)
forwards to every adapter in the ``orchestrator.preprint`` package,
that the credentials path resolution is platform-aware, and that the
SWORD pathway honours ``user\\npass`` two-line token files.
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from plugins.vedix.mcp.lib.orchestrator.hooks import preprint_submit


def _pdf(tmp_path: Path) -> Path:
    p = tmp_path / "ms.pdf"
    p.write_bytes(b"%PDF-1.4\n")
    return p


def test_valid_targets_now_include_sword() -> None:
    assert "sword" in preprint_submit.VALID_TARGETS
    assert {"arxiv", "biorxiv", "osf", "ssrn", "sword"} <= (
        preprint_submit.VALID_TARGETS
    )


def test_unknown_target_returns_error(tmp_path: Path) -> None:
    pdf = _pdf(tmp_path)
    out = preprint_submit.submit(
        target="not-a-server",
        manuscript_pdf=pdf,
        metadata={"title": "T"},
        dry_run=True,
    )
    assert out["status"] == "error"
    assert "unsupported" in out["reason"]
    assert "sword" in out["valid_targets"]


def test_missing_pdf_short_circuits_with_target(tmp_path: Path) -> None:
    out = preprint_submit.submit(
        target="osf",
        manuscript_pdf=tmp_path / "missing.pdf",
        metadata={},
        dry_run=True,
    )
    assert out["status"] == "error"
    assert "not found" in out["reason"]
    assert out["target"] == "osf"


@pytest.mark.parametrize(
    "target,expected_status",
    [
        ("arxiv", "dry-run"),
        ("biorxiv", "dry-run"),
        ("osf", "dry-run"),
        ("ssrn", "dry-run"),
        ("sword", "dry-run"),
    ],
)
def test_dry_run_routes_to_every_adapter(
    tmp_path: Path, target: str, expected_status: str
) -> None:
    pdf = _pdf(tmp_path)
    out = preprint_submit.submit(
        target=target,
        manuscript_pdf=pdf,
        metadata={"title": "T", "authors": ["A"]},
        dry_run=True,
    )
    assert out["status"] == expected_status
    assert out["target"] == target


def test_target_normalisation_case_insensitive(tmp_path: Path) -> None:
    pdf = _pdf(tmp_path)
    out = preprint_submit.submit(
        target="ArXiv",
        manuscript_pdf=pdf,
        metadata={"title": "T"},
        dry_run=True,
    )
    assert out["target"] == "arxiv"


def test_credentials_path_uses_userprofile_on_windows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("HOME", raising=False)
    p = preprint_submit._credentials_for("arxiv")
    assert p == tmp_path / ".vedix" / "byok" / "secrets" / "arxiv.token"


def test_credentials_path_uses_home_on_posix(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("USERPROFILE", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    p = preprint_submit._credentials_for("biorxiv")
    assert p == tmp_path / ".vedix" / "byok" / "secrets" / "biorxiv.token"


def test_arxiv_real_run_calls_adapter_with_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end: real-run path reads the token file and invokes httpx."""
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("HOME", raising=False)
    token_path = tmp_path / ".vedix" / "byok" / "secrets" / "arxiv.token"
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text("real-token", encoding="utf-8")

    from unittest.mock import MagicMock

    fake_resp = MagicMock(status_code=201, text="created")
    fake_resp.json = lambda: {"submission_id": "X-123"}
    pdf = _pdf(tmp_path)
    with patch("httpx.Client.post", return_value=fake_resp) as p:
        out = preprint_submit.submit(
            target="arxiv",
            manuscript_pdf=pdf,
            metadata={
                "title": "Real Run",
                "abstract": "Body",
                "authors": ["A"],
                "categories": ["cs.LG"],
            },
            dry_run=False,
        )
        _, kwargs = p.call_args
        assert kwargs["headers"]["Authorization"] == "Bearer real-token"
    assert out["status"] == "ok"
    assert out["submission_id"] == "X-123"


def test_sword_two_line_token_file_parsed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("HOME", raising=False)
    token_path = tmp_path / ".vedix" / "byok" / "secrets" / "sword.token"
    token_path.parent.mkdir(parents=True, exist_ok=True)
    # ``user\npass`` two-line format.
    token_path.write_text("alice\nhunter2\n", encoding="utf-8")

    from unittest.mock import MagicMock

    fake_resp = MagicMock(
        status_code=201,
        text="ok",
        headers={"Location": "https://ir.example.edu/deposits/1"},
    )
    pdf = _pdf(tmp_path)
    with patch("httpx.Client.post", return_value=fake_resp) as p:
        out = preprint_submit.submit(
            target="sword",
            manuscript_pdf=pdf,
            metadata={"title": "T"},
            dry_run=False,
            sword_endpoint="https://ir.example.edu/swordv2/collection/1",
        )
        _, kwargs = p.call_args
        # base64("alice:hunter2") == "YWxpY2U6aHVudGVyMg=="
        assert (
            kwargs["headers"]["Authorization"]
            == "Basic YWxpY2U6aHVudGVyMg=="
        )
    assert out["status"] == "ok"
    assert out["deposit_url"] == "https://ir.example.edu/deposits/1"


def test_sword_real_run_without_endpoint_returns_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("HOME", raising=False)
    pdf = _pdf(tmp_path)
    out = preprint_submit.submit(
        target="sword",
        manuscript_pdf=pdf,
        metadata={"title": "T"},
        dry_run=False,
        # no sword_endpoint kwarg
    )
    assert out["status"] == "error"
    assert "sword_endpoint" in out["reason"]


def test_sword_real_run_without_credentials_returns_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("HOME", raising=False)
    pdf = _pdf(tmp_path)
    out = preprint_submit.submit(
        target="sword",
        manuscript_pdf=pdf,
        metadata={"title": "T"},
        dry_run=False,
        sword_endpoint="https://ir.example.edu/swordv2/collection/1",
    )
    assert out["status"] == "error"
    assert "credentials" in out["reason"].lower()


def test_sword_username_password_kwargs_take_priority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Explicit kwargs win over the token file."""
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("HOME", raising=False)
    token_path = tmp_path / ".vedix" / "byok" / "secrets" / "sword.token"
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text("file-user\nfile-pass\n", encoding="utf-8")

    from unittest.mock import MagicMock

    fake = MagicMock(status_code=201, text="ok", headers={"Location": "x"})
    pdf = _pdf(tmp_path)
    with patch("httpx.Client.post", return_value=fake) as p:
        preprint_submit.submit(
            target="sword",
            manuscript_pdf=pdf,
            metadata={"title": "T"},
            dry_run=False,
            sword_endpoint="https://ir.example.edu/swordv2/collection/1",
            username="kw-user",
            password="kw-pass",
        )
        _, kwargs = p.call_args
        import base64

        assert (
            kwargs["headers"]["Authorization"]
            == "Basic " + base64.b64encode(b"kw-user:kw-pass").decode()
        )
