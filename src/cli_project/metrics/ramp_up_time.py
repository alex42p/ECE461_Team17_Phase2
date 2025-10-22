"""
DOCTYPE: Ramp-Up Time metric for documentation usability.
This module defines RampUpTimeMetric, which uses an LLM to analyze the README/
model card for documentation quality. It rates ramp-up readiness across several
dimensions (doc completeness, installability, quickstart, config clarity,
troubleshooting), combines them into an overall score, and returns details for
transparency.
"""

from __future__ import annotations
import time
from typing import Any, Dict

from src.cli_project.metrics.base import Metric, MetricResult, clamp01
from src.cli_project.adapters.llm_v0 import fetch_ramp_up_time_with_llm


class RampUpTimeMetric(Metric):
    """Evaluate ramp-up readiness of a model repo using an LLM."""

    @property
    def name(self) -> str:
        return "ramp_up_time"

    def compute(self, metadata: dict[str, Any]) -> MetricResult:
        t0 = time.time()

        repo_url = metadata["hf_metadata"].get("repo_url")
        if not repo_url:
            return MetricResult(
                name=self.name,
                value=0.0,
                details={"error": "Missing repo_url"},
                latency_ms=0,
            )

        try:
            llm_result: Dict[str, Any] = fetch_ramp_up_time_with_llm(repo_url)

            score = clamp01(llm_result.get("score", 0.0))
            details = {
                "doc_completeness": llm_result.get("doc_completeness", 0.0),
                "installability": llm_result.get("installability", 0.0),
                "quickstart": llm_result.get("quickstart", 0.0),
                "config_clarity": llm_result.get("config_clarity", 0.0),
                "troubleshooting": llm_result.get("troubleshooting", 0.0),
                "justification": llm_result.get("justification", ""),
            }
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
            details=details,
            latency_ms=latency,
        )
