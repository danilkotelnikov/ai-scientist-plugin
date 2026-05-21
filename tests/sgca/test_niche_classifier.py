import pytest
from unittest.mock import patch
from plugins.vedix.mcp.lib.orchestrator.sgca.niche_classifier import (
    NicheClassifier, load_niches, classify_niche,
)


def test_load_niches_returns_all_disciplines():
    niches = load_niches()
    assert "chemistry" in niches
    assert "photochemistry" in niches["chemistry"]


def test_niche_classifier_routes_obvious_topic():
    # Mock embeddings so the test is deterministic
    with patch("plugins.vedix.mcp.lib.orchestrator.sgca.niche_classifier._topic_label_cosine",
               side_effect=lambda t, l: 0.95 if "photochem" in l else 0.1):
        result = classify_niche(discipline="chemistry",
                                topic_text="UV-vis triplet sensitization of organic dyes")
        assert result == "chemistry/photochemistry"


def test_niche_classifier_falls_back_to_general_below_threshold():
    with patch("plugins.vedix.mcp.lib.orchestrator.sgca.niche_classifier._topic_label_cosine",
               return_value=0.2):
        result = classify_niche(discipline="chemistry", topic_text="something obscure")
        assert result == "chemistry/general"


def test_user_extension_via_local_yaml(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    (tmp_path / ".vedix").mkdir()
    (tmp_path / ".vedix" / "niches.local.yaml").write_text(
        "niches:\n  chemistry:\n    - novel_user_niche\n", encoding="utf-8")
    niches = load_niches()
    assert "novel_user_niche" in niches["chemistry"]
