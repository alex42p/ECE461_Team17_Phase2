"""
DOCTYPE: License metric for legal clarity and compatibility.
This module defines LicenseMetric, which inspects Hugging Face API metadata to
determine the declared license. It returns a binary score normalized to [0,1]:
1.0 only if the license is clearly one of MIT, Apache-2.0, BSD (2/3), or
LGPL-2.1; otherwise 0.0. The metric uses only the Hugging Face API 'license'
field. If that field is missing or unrecognized, the score is 0.0. The metric
also records the computation latency in milliseconds.
"""

from __future__ import annotations
import time
from typing import Any, Optional

from metric import Metric, MetricResult

# -------------------------------------------------------------------
# License Metric
# -------------------------------------------------------------------
class LicenseMetric(Metric):
    def __init__(self) -> None:
        super().__init__()
        self.ALLOWED = {
            "mit", "apache-2.0", "bsd", "lgpl", "cc0-1.0",
        }
        self.PROBLEMATIC = {
            "gpl", "agpl", "cc-by-nc", "proprietary"
        }

    def _norm(self, s: Optional[str]) -> str:
        if not s:
            return ""
        s = s.lower()
        if "mit" in s:
            return "mit"
        if "apache" in s:
            return "apache-2.0"
        if "bsd" in s:
            return "bsd"
        if "lgpl" in s and "2.1" in s:
            return "lgpl-2.1"
        if "agpl" in s:
            return "agpl"
        if "gpl" in s:
            return "gpl"
        if "cc-" in s:
            return "cc-by-nc"
        if "cc" in s:
            return "cc0-1.0"
        if "proprietary" in s:
            return "proprietary"
        return s.strip()
    
    @property
    def name(self) -> str:
        return "license"

    def compute(self, metadata: dict[str, Any]) -> MetricResult:
        """
        Compute license score from API metadata dict.
        """
        t0 = time.time()

        raw_license = metadata["hf_metadata"].get("license")
        lic_norm = self._norm(raw_license)

        score = 1.0 if lic_norm in self.ALLOWED else 0.4 if lic_norm in self.PROBLEMATIC else 0.0
        latency = int((time.time() - t0) * 1000)

        return MetricResult(
            name=self.name,
            value=score,
            details={"license": raw_license, "normalized": lic_norm},
            latency_ms=latency,
        )