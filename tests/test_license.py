import pytest
from src.license import LicenseMetric

def test_license_metric_init():
    metric = LicenseMetric()
    assert metric.name == "license"
    assert isinstance(metric.ALLOWED, set)
    assert isinstance(metric.PROBLEMATIC, set)

def test_license_normalization():
    metric = LicenseMetric()
    
    # Test various license strings
    assert metric._norm("MIT") == "mit"
    assert metric._norm("Apache License 2.0") == "apache-2.0"
    assert metric._norm("BSD-3-Clause") == "bsd"
    assert metric._norm("LGPL 2.1") == "lgpl"
    assert metric._norm("GPL-3.0") == "gpl"
    assert metric._norm("AGPL") == "agpl"
    assert metric._norm("CC-BY-NC 4.0") == "cc-by-nc"
    assert metric._norm("CC0") == "cc0-1.0"
    assert metric._norm("Proprietary") == "proprietary"
    assert metric._norm(None) == ""
    assert metric._norm("") == ""

def test_license_compute():
    metric = LicenseMetric()
    
    # Test allowed licenses
    allowed_licenses = ["MIT", "Apache 2.0", "BSD-3-Clause", "LGPL-2.1"]
    for license in allowed_licenses:
        result = metric.compute({"hf_metadata": {"license": license}})
        assert result.value == 1.0
        assert result.name == "license"
        assert "license" in result.details
        assert "normalized" in result.details
        assert result.latency_ms >= 0

    # Test problematic licenses
    problematic_licenses = ["GPL-3.0", "AGPL", "CC-BY-NC 4.0", "Proprietary"]
    for license in problematic_licenses:
        result = metric.compute({"hf_metadata": {"license": license}})
        assert result.value == 0.4
        assert "license" in result.details
        assert "normalized" in result.details

    # Test unknown/missing licenses
    unknown_cases = [
        {"hf_metadata": {"license": "Unknown"}},
        {"hf_metadata": {"license": None}},
        {"hf_metadata": {"license": ""}},
        {"hf_metadata": {}}
    ]
    for case in unknown_cases:
        result = metric.compute(case)
        assert result.value == 0.0
        assert "license" in result.details
        assert "normalized" in result.details