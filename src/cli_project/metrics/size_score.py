"""
DOCTYPE: SizeScoreMetric for model deployment suitability.

This metric estimates model size suitability across four device types
(Raspberry Pi, Jetson Nano, Desktop PC, AWS Server) using size metadata
from Hugging Face (`size_mb`).

Each device has a defined "sweet spot" size range. Models score:
- 1.0 when inside the sweet spot,
- less than 1.0 when smaller or larger (scaled by distance to range).
Returns a per-device score dictionary and latency in milliseconds.
"""

import time
from src.cli_project.metrics.base import Metric, MetricResult, validate_size_score_map
from typing import Any

DEVICE_THRESHOLDS = {
    "raspberry_pi": (50, 200),
    "jetson_nano": (200, 800),
    "desktop_pc": (500, 2000),
    "aws_server": (1000, 5000),
}

class SizeScoreMetric(Metric):
    """
    Computes per-device size suitability scores for model deployment,
    and reports latency of score computation.
    """
    @property
    def name(self) -> str:
        return "size_score"

    def compute(self, metadata: dict[str, Any]) -> MetricResult:
        t0 = time.time()
        size_mb = metadata["hf_metadata"].get("size_mb", 0)
        scores = {}

        for device, (min_mb, max_mb) in DEVICE_THRESHOLDS.items():
            if min_mb <= size_mb <= max_mb:
                score = 1.0
            elif size_mb < min_mb and min_mb > 0:
                score = size_mb / min_mb
            elif size_mb > max_mb and size_mb > 0:
                score = max_mb / size_mb
            else:
                score = 0.0

            scores[device] = round(min(max(score, 0.0), 1.0), 3)

        scores = validate_size_score_map(scores)
        latency = int((time.time() - t0) * 1000)

        return MetricResult(
            name=self.name,
            value=scores,
            details={"size_mb": size_mb},
            latency_ms=latency,
        )
