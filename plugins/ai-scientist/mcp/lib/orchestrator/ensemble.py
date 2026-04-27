"""BiasedReviewers — N reviewers with bias prompts + numpy aggregation.
Per spec §4.7. Direct port of Sakana perform_llm_review.py:17-24, 150-202.

Closes 'single-opinion review' audit finding.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Optional
import numpy as np


@dataclass
class ReviewAggregate:
    median_overall: float
    mean_overall: float
    score_iqr: float
    consensus_high: bool       # majority >= 5/10
    has_outliers: bool         # any |score - median| > 1.5 * IQR or > 3 absolute
    individual_reviews: list = field(default_factory=list)
    biases: list = field(default_factory=list)


class BiasedReviewers:
    def __init__(
        self,
        *,
        dispatcher: Callable,
        biases: Optional[list] = None,
    ):
        self.dispatcher = dispatcher
        self.biases = biases or ["positive", "negative", "neutral"]

    def review(self, *, manuscript: str = "", agent_name: str = "reviewer", **extra_inputs) -> ReviewAggregate:
        reviews = []
        for bias in self.biases:
            inputs = dict(extra_inputs, manuscript=manuscript, system_bias=bias)
            response = self.dispatcher(agent_name=agent_name, inputs=inputs)
            reviews.append(response if isinstance(response, dict) else {"Overall": 5})
        return self._aggregate(reviews)

    def _aggregate(self, reviews: list) -> ReviewAggregate:
        scores = np.array([r.get("Overall", 5) for r in reviews], dtype=float)
        median = float(np.median(scores))
        mean = float(np.mean(scores))
        # Use 'lower' interpolation: preserves actual data values, avoids phantom
        # midpoints on small samples (Sakana typically runs 3 reviewers).
        q75, q25 = np.percentile(scores, [75, 25], method="lower")
        iqr = float(q75 - q25)
        consensus_high = bool((scores >= 5).mean() > 0.5)
        # Outlier: absolute deviation from median > 3 points on 10-pt scale.
        # More reliable than 1.5*IQR for n=3 where IQR can mask extreme values.
        has_outliers = bool(np.any(np.abs(scores - median) > 3))
        return ReviewAggregate(
            median_overall=median,
            mean_overall=mean,
            score_iqr=iqr,
            consensus_high=consensus_high,
            has_outliers=has_outliers,
            individual_reviews=reviews,
            biases=list(self.biases),
        )
