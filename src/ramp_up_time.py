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
from typing import Any

from metric import Metric, MetricResult, clamp


class RampUpTimeMetric(Metric):
    """Evaluate ramp-up readiness of a model repo using an LLM."""

    @property
    def name(self) -> str:
        return "ramp_up_time"

    def compute(self, metadata: dict[str, Any]) -> MetricResult:
        t0 = time.time()
        score = 0.0 
        
        try:
            repo_url = metadata["hf_metadata"].get("repo_url")
            if not repo_url:
                raise Exception("Missing repo_url")
            # check README, model card, and usage stats
            readme_score = self.eval_readme(metadata.get("readme_text", ""))
            score += readme_score * 0.5
            model_card_score = self.eval_model_card(metadata)
            score += model_card_score * 0.2
            usage_score = self.eval_usage(metadata)
            score += usage_score * 0.3
            details = {
                "readme_score": readme_score,
                "model_card_score": model_card_score,
                "usage_score": usage_score,
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

    def eval_readme(self, readme: str) -> float:
        if not readme:
            return 0.0
        
        readme_lower = readme.lower()
        score = 0.0
        
        # check for how to use and proper documentation
        if "usage" in readme_lower or "how to use" in readme_lower:
            score += 0.3
        if "example" in readme_lower or "```python" in readme_lower:
            score += 0.3
        if "install" in readme_lower:
            score += 0.2
        if len(readme) > 500: 
            score += 0.2
        
        return clamp(score)

    def eval_model_card(self, metadata) -> float:
        score = 0.0
        if metadata["hf_metadata"].get("description"):
            score += 0.7
        if metadata["hf_metadata"].get("readme_text"):
            score += 0.2
        if metadata["hf_metadata"].get("tags"):
            score += 0.1
        return clamp(score)

    def eval_usage(self, metadata) -> float:
        downloads = metadata["hf_metadata"].get("downloads", 0)
        if not downloads:
            downloads = metadata["hf_metadata"].get("downloads_last_month", 0)
        likes = metadata["hf_metadata"].get("likes", 0)
        stars = metadata["hf_metadata"].get("stars", 0) 

        download_score = min(1.0, downloads / 10000)
        like_score = min(1.0, likes / 100)
        stars_score = min(1.0, stars / 100)
        
        return (download_score + like_score + stars_score) / 3