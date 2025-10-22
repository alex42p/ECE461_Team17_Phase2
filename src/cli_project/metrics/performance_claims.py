"""
DOCTYPE: Performance Claims metric for self-reported results.
This module defines PerformanceClaimsMetric, which uses an LLM to scan the
README/model card for author-reported performance metrics (e.g., accuracy, F1,
BLEU, ROUGE, mAP, precision/recall). The LLM extracts numeric claims,
normalizes them into [0,1], and returns both the individual claims and an
overall average score. If no claims are found, the score is 0.0. Because these
are self-reported, this metric is lightly weighted elsewhere.
"""

from __future__ import annotations
import time
from typing import Any, Dict

from src.cli_project.metrics.base import Metric, MetricResult, clamp01
from src.cli_project.adapters.llm_v0 import fetch_performance_claims_with_llm


class PerformanceClaimsMetric(Metric):
    """Extract and score self-reported performance metrics using an LLM."""

    @property
    def name(self) -> str:
        return "performance_claims"

    def compute(self, metadata: dict[str, Any]) -> MetricResult:
        t0 = time.time()
        
        repo_url: str = metadata["hf_metadata"].get("repo_url")
        if not repo_url:
            return MetricResult(
                name=self.name,
                value=0.0,
                details={"error": "Missing repo_url"},
                latency_ms=0,
            )


        try:
            llm_result: Dict[str, Any] = fetch_performance_claims_with_llm(repo_url)

            claims = llm_result.get("claims", {})
            score = clamp01(llm_result.get("score", 0.0))
        except Exception as e:
            return MetricResult(
                name=self.name,
                value=0.0,
                details={"error": str(e)},
                latency_ms=int((time.time() - t0) * 1000),
            )

        latency = int((time.time() - t0) * 1000)
        return MetricResult(
            name=self.name,
            value=score,
            details={"claims": claims},
            latency_ms=latency,
        )
