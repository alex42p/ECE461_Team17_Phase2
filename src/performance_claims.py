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
import re
from typing import Any, Dict

from metric import Metric, MetricResult, clamp

class PerformanceClaimsMetric(Metric):
    """Extract and score self-reported performance metrics using an LLM."""

    @property
    def name(self) -> str:
        return "performance_claims"

    def compute(self, metadata: dict[str, Any]) -> MetricResult:
        t0 = time.time()
        score = 0.0

        readme_score = self.eval_readme(metadata["hf_metadata"].get("readme_text", ""))
        score += readme_score * 0.8
        siblings_score = self.eval_siblings(metadata["hf_metadata"])
        score += siblings_score * 0.2
        
        latency = int((time.time() - t0) * 1000)
        return MetricResult(
            name=self.name,
            value=score,
            details={"success": True},
            latency_ms=latency,
        )

    def eval_readme(self, readme: str) -> float:
        """Look for performance metrics in README"""
        if not readme:
            return 0.0
        
        readme_lower = readme.lower()
        performance_indicators = {
            "accuracy", "f1", "bleu", "rouge", "perplexity", 
            "benchmark", "evaluation", "performance", "results"
        }

        score = 0.0
        # First check for numeric results with performance indicators
        has_numbers = bool(re.search(r'\d+\.\d+', readme))
        for indicator in performance_indicators:
            if indicator in readme_lower:
                if has_numbers:
                    score += 0.3  # More points for numeric results
                else:
                    score += 0.1  # Fewer points for just mentioning metrics
        
        return clamp(score)
    
    def eval_siblings(self, metadata: Dict[str, Any]) -> float:
        """Check for evaluation or benchmark files"""
        files = metadata.get("siblings", [])
        if not files:
            return 0.0
        
        testing_indicators = {"eval", "benchmark", "test", "metric"}
        
        for file_info in files:
            filename = file_info.get("rfilename", "").lower()
            for indicator in testing_indicators:
                if indicator in filename:
                    return 1.0
        
        return 0.2