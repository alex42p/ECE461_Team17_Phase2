"""
DOCTYPE: Base interfaces and types for scoring metrics.
This module defines the abstract Metric interface that all concrete metrics must
implement (a `name` property and a `compute(url: str) -> MetricResult` method),
the `MetricResult` dataclass that standardizes outputs (value, details,
latency_ms), and small helpers to keep metric values valid. Metric values are
floats in [0,1] for most metrics, or a {str -> float} map for `size_score`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Union

# ---------------------------------------------------------------------------

MetricValue = Union[float, Mapping[str, float]]

@dataclass(frozen=True, slots=True)
class MetricResult:
    """
    Standard envelope returned by every metric.

    Attributes
    ----------
    name : str
        Short identifier for the metric (e.g., "license", "bus_factor").
    value : MetricValue
        Normalized float in [0,1], or a {str -> float} map for size_score.
    details : dict[str, Any]
        Optional, human/machine-readable context about how the score was computed.
        Keep this small and JSON-serializable.
    latency_ms : int
        Time to compute this metric in milliseconds.
    """
    name: str
    value: MetricValue
    details: Dict[str, Any]
    latency_ms: int = 0

class Metric(ABC):
    """
    Abstract base class for all metrics.

    Implementors must provide:
      - `name` (property): a stable identifier.
      - `compute(url)`: returns a MetricResult for the given model URL.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """The metric's stable identifier (e.g., 'license')."""
        raise NotImplementedError

    @abstractmethod
    def compute(self, metadata: dict[str, Any]) -> MetricResult:
        """Compute this metric for the given Hugging Face model URL."""
        raise NotImplementedError

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def clamp01(x: float) -> float:
    """Clamp a float into [0,1]."""
    if x != x:  # NaN check
        return 0.0
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return float(x)

def validate_size_score_map(m: Mapping[str, float]) -> Dict[str, float]:
    """Validate and normalize a size_score map ({device -> score in [0,1]})."""
    out: Dict[str, float] = {}
    for k, v in m.items():
        key = str(k)
        val = float(v)

        out[key] = clamp01(val)
    return out
