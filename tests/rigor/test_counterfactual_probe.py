"""Tests for §4.3 counterfactual citation probing."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_generate_decoy_returns_plausible():
    from plugins.vedix.mcp.lib.orchestrator.counterfactual_probe import (
        generate_decoy,
    )
    real = {
        "year": 2024,
        "title": "Effect of solvent polarity on Diels-Alder kinetics",
    }
    fake = type(
        "R", (),
        {"content": 'Effect of temperature on Diels-Alder yield (Smith 2024)'},
    )()
    with patch(
        "plugins.vedix.mcp.lib.orchestrator.dispatch.dispatch_agent",
        new=AsyncMock(return_value=fake),
    ):
        decoy = await generate_decoy(real)
        assert decoy["year"] == 2024
        assert decoy["title"] != real["title"]


@pytest.mark.asyncio
async def test_probe_citation_classifies_load_bearing():
    from plugins.vedix.mcp.lib.orchestrator.counterfactual_probe import (
        probe_citation,
    )
    paragraph = "The reaction follows Diels-Alder kinetics [smith2024]."
    real = {"key": "smith2024", "title": "Diels-Alder kinetics"}
    decoy_title = "Cake recipe optimization"
    fake = type("R", (), {"content": "DIFFERENT"})()
    with patch(
        "plugins.vedix.mcp.lib.orchestrator.dispatch.dispatch_agent",
        new=AsyncMock(return_value=fake),
    ):
        verdict = await probe_citation(
            paragraph=paragraph,
            citation_key="smith2024",
            real=real,
            decoy_title=decoy_title,
        )
        assert verdict["load_bearing"] is True


@pytest.mark.asyncio
async def test_probe_citation_classifies_decorative():
    from plugins.vedix.mcp.lib.orchestrator.counterfactual_probe import (
        probe_citation,
    )
    paragraph = "Many reactions exist [smith2024]."
    real = {"key": "smith2024", "title": "Diels-Alder kinetics"}
    decoy_title = "Cake recipe optimization"
    fake = type("R", (), {"content": "SAME"})()
    with patch(
        "plugins.vedix.mcp.lib.orchestrator.dispatch.dispatch_agent",
        new=AsyncMock(return_value=fake),
    ):
        verdict = await probe_citation(
            paragraph=paragraph,
            citation_key="smith2024",
            real=real,
            decoy_title=decoy_title,
        )
        assert verdict["load_bearing"] is False
