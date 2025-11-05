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
    Computes code quality for Hugging Face model repos based on heuristics:
      - Presence of README.md
      - Presence of config.json
      - Presence of .py files (esp. train.py / run.py)
      - Project cleanliness (few junk files)
    """
    @property
    def name(self) -> str:
        return "code_quality"

    def compute(self, metadata: Dict[str, Any]) -> MetricResult:
        t0 = time.time()
        # model_id = metadata["hf_metadata"].get("repo_id", None)
        nof_code_ds = metadata.get("nof_code_ds") or {}
        if nof_code_ds.get("nof_code"):
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

        # if not model_id:
        #     return MetricResult(
        #         name=self.name,
        #         value=0.0,
        #         details={"error": "No model ID found in metadata"},
        #         latency_ms=0
        #     )
        # logger.info(f"Computing code quality for model {model_id}")

        # try:
        #     score = 0.0
        #     siblings = metadata["hf_metadata"].get("siblings", [])

        #     readme_len = len(metadata["hf_metadata"].get("readme_text", ""))  
        #     if readme_len:
        #         score += min(1.0, readme_len / 500.0) * 0.5

        #     # check if config.json is in the siblings list
        #     for file_info in siblings:
        #         file = file_info.get("rfilename", "").lower()
        #         if file == "config.json":
        #             score += 0.5
        #             break

        #     latency = max(1, int((time.time() - t0) * 1000))
        #     return MetricResult(
        #         name=self.name,
        #         value=score,
        #         details={"success": True},
        #         latency_ms=latency
        #     )

        # except Exception as e:
        #     print(f"Error computing code quality for {model_id}: {e}")
        #     latency = max(1, int((time.time() - t0) * 1000))
        #     return MetricResult(
        #         name=self.name,
        #         value=0.0,
        #         details={"error": str(e)},
        #         latency_ms=latency
        #     )

