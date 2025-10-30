import pytest
from src.size_score import SizeScoreMetric

def test_size_score_metric_init():
    metric = SizeScoreMetric()
    assert metric.name == "size_score"
    assert isinstance(metric.DEVICE_THRESHOLDS, dict)
    
    # Verify thresholds for each device
    expected_thresholds = {
        "raspberry_pi": 2000,
        "jetson_nano": 8000,
        "desktop_pc": 16000,
        "aws_server": 64000,
    }
    assert metric.DEVICE_THRESHOLDS == expected_thresholds

def test_size_score_compute():
    metric = SizeScoreMetric()
    
    # Test different model sizes
    test_cases = [
        (1000, {  # Small model (1GB)
            "raspberry_pi": 1.0,
            "jetson_nano": 1.0,
            "desktop_pc": 1.0,
            "aws_server": 1.0
        }),
        (3000, {  # Medium model (3GB)
            "raspberry_pi": 0.667,
            "jetson_nano": 1.0,
            "desktop_pc": 1.0,
            "aws_server": 1.0
        }),
        (10000, {  # Large model (10GB)
            "raspberry_pi": 0.2,
            "jetson_nano": 0.8,
            "desktop_pc": 1.0,
            "aws_server": 1.0
        }),
        (100000, {  # Very large model (100GB)
            "raspberry_pi": 0.02,
            "jetson_nano": 0.08,
            "desktop_pc": 0.16,
            "aws_server": 0.64
        }),
        (0, {  # Zero size
            "raspberry_pi": 0.0,
            "jetson_nano": 0.0,
            "desktop_pc": 0.0,
            "aws_server": 0.0
        })
    ]
    
    for size_mb, expected_scores in test_cases:
        result = metric.compute({"hf_metadata": {"size_mb": size_mb}})
        assert result.name == "size_score"
        assert isinstance(result.value, dict)
        assert set(result.value.keys()) == set(metric.DEVICE_THRESHOLDS.keys())
        assert result.details == {"size_mb": size_mb}
        assert result.latency_ms >= 0
        
        # Check each device score with rounding to handle floating point precision
        for device, expected_score in expected_scores.items():
            actual_score = result.value[device]
            assert round(actual_score, 3) == expected_score, \
                f"Device {device} with size {size_mb}MB: expected {expected_score}, got {actual_score}"

def test_size_score_with_missing_data():
    metric = SizeScoreMetric()
    
    # Test with missing or invalid size data
    test_cases = [
        {"hf_metadata": {}},  # Missing size_mb
        {"hf_metadata": {"size_mb": None}},  # None size
        {"hf_metadata": {"size_mb": "invalid"}},  # Invalid size
    ]
    
    for metadata in test_cases:
        result = metric.compute(metadata)
        assert result.name == "size_score"
        assert isinstance(result.value, dict)
        assert all(score == 0.0 for score in result.value.values())