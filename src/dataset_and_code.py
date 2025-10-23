"""
DOCTYPE: Dataset & Code availability metric (reproducibility & usability).

This metric checks whether a model clearly documents its training/benchmark
datasets and provides runnable code (examples, scripts, or notebooks).
It aggregates two sub-signals—dataset presence and code presence—into
a single score in [0,1] with equal weights (0.5 each).
"""

from __future__ import annotations
import re, time
from typing import Any, Dict

from metric import Metric, MetricResult, clamp


# -----------------------
# Helpers
# -----------------------

_DATASET_KEYWORDS = [
    r"\bdataset\b", r"\bdatasets\b",
    r"\btraining data\b", r"\btrain(?:ed)? on\b",
    r"\bevaluation data\b", r"\bbenchmark(?:s)?\b",
    r"\bdata source\b", r"\bcorpus\b",
]

_CODE_KEYWORDS = [
    r"\bexample(?:s)?\b", r"\busage\b", r"\bquickstart\b",
    r"\bhow to run\b", r"\brun the model\b",
    r"\btrain(?:ing)? script\b", r"\beval(?:uation)? script\b",
    r"\bnotebook\b", r"\bcolab\b",
]


def _contains_keywords(text: str, patterns: list[str]) -> bool:
    """Check if text contains any of the given keyword regex patterns."""
    if not text:
        return False
    for p in patterns:
        if re.search(p, text, flags=re.IGNORECASE):
            return True
    return False


# -----------------------
# Metric implementation
# -----------------------

class DatasetAndCodeMetric(Metric):
    """Binary-evidence metric: dataset mentioned + code available → higher score."""

    W_DATASET: float = 0.5
    W_CODE: float = 0.5

    @property
    def name(self) -> str:
        return "dataset_and_code_score"

    def compute(self, metadata: dict[str, Any]) -> MetricResult:
        t0 = time.time()

        # -----------------
        # Dataset evidence
        # -----------------
        has_dataset_url = bool(metadata["nof_code_ds"].get("nof_ds"))
        readme_text = metadata.get("readme_text", "")
        mentions_dataset = _contains_keywords(readme_text, _DATASET_KEYWORDS)

        dataset_present = has_dataset_url or mentions_dataset

        # -------------
        # Code evidence
        # -------------
        has_repo_url = bool(metadata["nof_code_ds"].get("nof_code"))
        mentions_code = _contains_keywords(readme_text, _CODE_KEYWORDS)

        code_present = has_repo_url or mentions_code

        # -----------------
        # Aggregate score
        # -----------------
        score = clamp(
            self.W_DATASET * (1.0 if dataset_present else 0.0) +
            self.W_CODE    * (1.0 if code_present else 0.0)
        )

        latency = int((time.time() - t0) * 1000)

        details: Dict[str, Any] = {
            "dataset_present": dataset_present,
            "dataset_signals": {
                "has_dataset_url": has_dataset_url,
                "mentions_dataset": mentions_dataset,
            },
            "code_present": code_present,
            "code_signals": {
                "has_repo_url": has_repo_url,
                "mentions_code": mentions_code,
            },
        }

        return MetricResult(
            name=self.name,
            value=score,
            details=details,
            latency_ms=latency,
        )
