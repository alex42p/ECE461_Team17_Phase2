import pytest
from src.code_quality import CodeQualityMetric

def test_code_quality_metric_init():
    metric = CodeQualityMetric()
    assert metric.name == "code_quality"

def test_compute():
    metric = CodeQualityMetric()

    # Test with code repo present (should return 1.0)
    metadata_with_code = {
        "nof_code_ds": {"nof_code": 1},
        "hf_metadata": {
            "repo_id": "org/good-model",
            "readme_text": "Comprehensive documentation" * 50,
            "siblings": [
                {"rfilename": "config.json"},
                {"rfilename": "train.py"},
                {"rfilename": "model.py"},
                {"rfilename": "utils.py"}
            ]
        }
    }
    result = metric.compute(metadata_with_code)
    assert isinstance(result.value, float)
    assert result.value == 1.0
    assert result.name == "code_quality"
    assert result.details["success"] is True
    assert result.latency_ms >= 1

    # Test with no code repo (should return 0.0)
    metadata_no_code = {
        "nof_code_ds": {"nof_code": 0},
        "hf_metadata": {
            "repo_id": "org/poor-model",
            "readme_text": "",
            "siblings": [
                {"rfilename": "model.bin"}
            ]
        }
    }
    result = metric.compute(metadata_no_code)
    assert result.value == 0.0
    assert "error" in result.details
    assert result.latency_ms == 0

    # Test with missing nof_code_ds (should return 0.0)
    missing_code_ds_metadata = {
        "hf_metadata": {
            "repo_id": "org/poor-model",
            "readme_text": "",
            "siblings": [
                {"rfilename": "model.bin"}
            ]
        }
    }
    result = metric.compute(missing_code_ds_metadata)
    assert result.value == 0.0
    assert "error" in result.details
    assert result.latency_ms == 0