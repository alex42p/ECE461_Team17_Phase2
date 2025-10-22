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
# Allowed licenses
# -------------------------------------------------------------------
ALLOWED = {
    "mit", "apache-2.0", "bsd-2-clause", "bsd-3-clause", "bsd",
    "lgpl-2.1", "lgpl-2.1-only", "lgpl-2.1-or-later"
}

# -------------------------------------------------------------------
# Normalizer
# -------------------------------------------------------------------
def _norm(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    s = s.lower()
    if "mit" in s:
        return "mit"
    if "apache" in s and "2.0" in s:
        return "apache-2.0"
    if "bsd-3" in s or ("bsd" in s and "3" in s):
        return "bsd-3-clause"
    if "bsd-2" in s or ("bsd" in s and "2" in s):
        return "bsd-2-clause"
    if s.strip() == "bsd":
        return "bsd"
    if "lgpl" in s and "2.1" in s and "3.0" not in s:
        return "lgpl-2.1"
    if "lgpl" in s and "3.0" in s:
        return "lgpl-3.0"
    return s.strip()

# -------------------------------------------------------------------
# License Metric
# -------------------------------------------------------------------
class LicenseMetric(Metric):
    @property
    def name(self) -> str:
        return "license"

    def compute(self, metadata: dict[str, Any]) -> MetricResult:
        """
        Compute license score from API metadata dict.
        """
        t0 = time.time()

        raw_license = metadata["hf_metadata"].get("license")
        # raw_license = metadata[metadata["hf_metadata"]]
        lic_norm = _norm(raw_license)

        score = 1.0 if lic_norm in ALLOWED else 0.0
        latency = int((time.time() - t0) * 1000)

        return MetricResult(
            name=self.name,
            value=score,
            details={"license": raw_license, "normalized": lic_norm},
            latency_ms=latency,
        )
