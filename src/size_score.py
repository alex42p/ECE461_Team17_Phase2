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
from metric import Metric, MetricResult, clamp
from typing import Any


class SizeScoreMetric(Metric):
    """
    Computes per-device size suitability scores for model deployment,
    and reports latency of score computation.
    """
    def __init__(self) -> None:
        super().__init__()
        self.DEVICE_THRESHOLDS = {
            "raspberry_pi": 2000,
            "jetson_nano": 8000,
            "desktop_pc": 16000,
            "aws_server": 64000,
        }

    @property
    def name(self) -> str:
        return "size_score"

    def compute(self, metadata: dict[str, Any]) -> MetricResult:
        t0 = time.time()
        try:
            storage_size = float(metadata["hf_metadata"].get("size_mb", 0))
        except (TypeError, ValueError):
            storage_size = 0

        scores = {}
        for device, max_mb in self.DEVICE_THRESHOLDS.items():
            usage = max_mb / storage_size if storage_size > 0 else 0.0
            scores[device] = round(usage, 3) if usage <= 1.0 else 1.0

        # scores = validate_size_score_map(scores) # REDUNDANT USELESS FUCKING CODE
        latency = max(1, int((time.time() - t0) * 1000))

        return MetricResult(
            name=self.name,
            value=scores,
            details={"size_mb": storage_size},
            latency_ms=latency,
        )
