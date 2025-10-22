"""
DOCTYPE: Bus Factor metric for repository sustainability.
This module defines BusFactorMetric, which inspects the number of unique recent
committers (from metadata) and estimates the project's resilience to developer
loss. It normalizes the committer count into [0,1] by dividing by 10 and capping
at 1.0: a repo with ≥10 active committers scores 1.0, while 0 committers scores
0.0. The metric also includes details showing the raw count.
"""

from __future__ import annotations
import time
from typing import Any, Dict

from metric import Metric, MetricResult, clamp01


class BusFactorMetric(Metric):
    """Assess knowledge distribution in the repo via recent committer count."""

    @property
    def name(self) -> str:
        return "bus_factor"

    def compute(self, metadata: dict[str, Any]) -> MetricResult:
        t0 = time.time()

        # Get raw number of recent committers from metadata (adapter must provide this)
        n_committers = metadata["repo_metadata"].get("recent_committers", 0)
        if not isinstance(n_committers, (int, float)):
            n_committers = 0

        # Normalize: simple linear scale up to 10 contributors
        val = clamp01(n_committers / 10.0)

        details: Dict[str, int] = {"recent_committers": int(n_committers)}

        return MetricResult(
            name=self.name,
            value=val,
            details=details,
            latency_ms=int((time.time() - t0) * 1000),
        )
