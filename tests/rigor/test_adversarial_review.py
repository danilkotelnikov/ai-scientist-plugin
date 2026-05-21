"""Tests for §4.4 adversarial multi-pass review."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_two_pass_steelman_break_returns_median_and_disagreement():
    from plugins.vedix.mcp.lib.orchestrator.adversarial_review import (
        review_with_stances,
    )
    side_effects = [
        type("R", (), {"content": '{"score": 8, "rationale": "strong"}'})(),
        type("R", (), {"content": '{"score": 4, "rationale": "weak"}'})(),
    ]
    with patch(
        "plugins.vedix.mcp.lib.orchestrator.dispatch.dispatch_agent",
        new=AsyncMock(side_effect=side_effects),
    ):
        result = await review_with_stances(
            manuscript_text="dummy", n_passes=2,
        )
        assert result["median_score"] == 6
        assert result["disagreement"] == 4
        assert len(result["passes"]) == 2
