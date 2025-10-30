import pytest
from src.code_quality import CodeQualityMetric

def test_code_quality_metric_init():
    metric = CodeQualityMetric()
    assert metric.name == "code_quality"

def test_compute():
    metric = CodeQualityMetric()
    
    # Test with good code structure
    good_metadata = {
        "hf_metadata": {
            "repo_id": "org/good-model",
            "readme_text": "Comprehensive documentation" * 50,  # > 500 chars
            "siblings": [
                {"rfilename": "config.json"},
                {"rfilename": "train.py"},
                {"rfilename": "model.py"},
                {"rfilename": "utils.py"}
            ]
        }
    }
    result = metric.compute(good_metadata)
    assert isinstance(result.value, float)
    assert result.value == 1.0  # Should be maximum score
    assert result.name == "code_quality"
    assert result.details["success"] is True
    assert result.latency_ms >= 0
    
    # Test with moderate code structure
    moderate_metadata = {
        "hf_metadata": {
            "repo_id": "org/moderate-model",
            "readme_text": "Basic documentation",  # < 500 chars
            "siblings": [
                {"rfilename": "config.json"},
                {"rfilename": "model.py"}
            ]
        }
    }
    result = metric.compute(moderate_metadata)
    assert isinstance(result.value, float)
    assert 0 < result.value < 1.0  # Should be partial score
    
    # Test with poor code structure
    poor_metadata = {
        "hf_metadata": {
            "repo_id": "org/poor-model",
            "readme_text": "",  # No documentation
            "siblings": [
                {"rfilename": "model.bin"}
            ]
        }
    }
    result = metric.compute(poor_metadata)
    assert result.value == 0.0  # Should be minimum score
    
    # Test missing repo_id
    missing_id_metadata = {
        "hf_metadata": {}
    }
    result = metric.compute(missing_id_metadata)
    assert result.value == 0.0
    assert "error" in result.details
    
    # Test with various README lengths
    readme_test_cases = [
        ("", 0.0),  # Empty
        ("Short readme", 0.1),  # Very short
        ("Medium length readme" * 10, 0.3),  # Medium
        ("Long readme" * 50, 0.5)  # Long enough for full readme score
    ]
    
    for readme_text, expected_readme_contribution in readme_test_cases:
        metadata = {
            "hf_metadata": {
                "repo_id": "org/test-model",
                "readme_text": readme_text,
                "siblings": []
            }
        }
        result = metric.compute(metadata)
        assert isinstance(result.value, float)
        assert result.value <= expected_readme_contribution
    
    # Test with various config file combinations
    config_test_cases = [
        ([{"rfilename": "config.json"}], 0.5),  # Has config
        ([{"rfilename": "model.py"}], 0.0),  # No config
        ([{"rfilename": "config.json"}, {"rfilename": "model.py"}], 0.5)  # Config with other files
    ]
    
    for siblings, expected_config_score in config_test_cases:
        metadata = {
            "hf_metadata": {
                "repo_id": "org/test-model",
                "readme_text": "",
                "siblings": siblings
            }
        }
        result = metric.compute(metadata)
        assert isinstance(result.value, float)
        assert abs(result.value - expected_config_score) < 0.01