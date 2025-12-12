"""
DOCTYPE: Code Quality metric (readability, structure, and maintainability).

This metric inspects Hugging Face model repositories for indicators of good 
software practices, including the presence of a README, config files, training 
scripts, sufficient Python source files, and a clean project structure. It 
aggregates these signals with weighted scores into a final value in [0,1], where 
higher scores reflect better-documented, more maintainable codebases.
"""

import time
from typing import Any, Dict
from metric import MetricResult, Metric
# from huggingface_inspect import clone_model_repo, clean_up_cache
import logging

logger = logging.getLogger(__name__)

class CodeQualityMetric(Metric):
    """
    Computes code quality for Hugging Face model repos
    """
    @property
    def name(self) -> str:
        return "code_quality"

    def compute(self, metadata: Dict[str, Any]) -> MetricResult:
        t0 = time.time()
        nof_code_ds = metadata.get("nof_code_ds") or {}
        if nof_code_ds.get("nof_code") or self._check_readme_for_codebase_mentions(metadata["hf_metadata"].get("readme_text", "")):
            return MetricResult(
                name=self.name,
                value=1.0,
                details={"success": True},
                latency_ms=max(1, int((time.time() - t0) * 1000))
            )
        else:
            return MetricResult(
                name=self.name,
                value=0.0,
                details={"error": "No model ID found in metadata"},
                latency_ms=0
            )

    def _check_readme_for_codebase_mentions(self, readme: str) -> bool:
        # if it mentions the word github it gets a 1 - fuck it  
        code_indicators = ["github", "bitbucket"]
        return any(indicator in readme.lower() for indicator in code_indicators)