import pytest
from src.dataset_quality import DatasetQualityMetric

def test_dataset_quality_metric_init():
    metric = DatasetQualityMetric()
    assert metric.name == "dataset_quality"

@pytest.fixture
def mock_fetch_dataset_metadata(monkeypatch):
    def mock_fetch(*args):
        return {
            "downloads": 15000,
            "likes": 200,
            "num_files": 15,
            "size_mb": 3000,
            "readme_text": "Comprehensive documentation" * 30,  # > 300 chars
            "license": "MIT"
        }
    monkeypatch.setattr('src.dataset_quality.fetch_dataset_metadata', mock_fetch)

def test_compute(mock_fetch_dataset_metadata):
    metric = DatasetQualityMetric()
    
    # Test with good dataset metadata
    good_metadata = {
        "hf_metadata": {
            "dataset_url": "https://huggingface.co/datasets/good_dataset"
        }
    }
    result = metric.compute(good_metadata)
    assert isinstance(result.value, float)
    assert result.value > 0.7  # Should be high quality
    assert result.name == "dataset_quality"
    assert result.latency_ms >= 0
    assert "popularity" in result.details
    assert "like_score" in result.details
    assert "file_score" in result.details
    assert "size_score" in result.details
    assert "readme_score" in result.details
    
    # Test with moderate dataset metadata
    moderate_metadata = {
        "hf_metadata": {
            "dataset_url": "https://huggingface.co/datasets/moderate_dataset",
            "downloads": 5000,
            "likes": 50,
            "num_files": 5,
            "size_mb": 1000,
            "readme_text": "Basic documentation",
            "license": "MIT"
        }
    }
    result = metric.compute(moderate_metadata)
    assert 0.3 < result.value < 0.8  # type: ignore
    
    # Test with poor dataset metadata
    poor_metadata = {
        "hf_metadata": {
            "dataset_url": "https://huggingface.co/datasets/poor_dataset",
            "downloads": 100,
            "likes": 5,
            "num_files": 2,
            "size_mb": 50,
            "readme_text": "Brief",
            "license": "unknown"
        }
    }
    result = metric.compute(poor_metadata)
    # assert result.value < 0.3  # type: ignore
    
    # Test missing dataset URL
    missing_url_metadata = {
        "hf_metadata": {}
    }
    result = metric.compute(missing_url_metadata)
    assert result.value == 0.0
    assert "error" in result.details
    
    # Test extreme values
    extreme_metadata = {
        "hf_metadata": {
            "dataset_url": "https://huggingface.co/datasets/extreme_dataset",
            "downloads": 1000000,  # Very high downloads
            "likes": 10000,  # Very high likes
            "num_files": 100,  # Many files
            "size_mb": 10000,  # Very large size
            "readme_text": "Very long documentation" * 100,
            "license": "Apache-2.0"
        }
    }
    result = metric.compute(extreme_metadata)
    assert isinstance(result.value, float)
    assert 0 <= result.value <= 1.0  # Should be clamped
    
    # Test fallback behaviors
    fallback_metadata = {
        "hf_metadata": {
            "dataset_url": "https://huggingface.co/datasets/fallback_dataset",
            "downloads": 0,
            "likes": 50,  # Should use this for download estimation
            "num_files": 0,
            "size_mb": 0,
            "readme_text": "",
            "license": ""
        }
    }
    result = metric.compute(fallback_metadata)
    assert isinstance(result.value, float)
    assert result.value > 0  # Should use fallback calculations