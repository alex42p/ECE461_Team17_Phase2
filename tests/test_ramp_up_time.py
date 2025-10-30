import pytest
from src.ramp_up_time import RampUpTimeMetric

def test_ramp_up_time_metric_init():
    metric = RampUpTimeMetric()
    assert metric.name == "ramp_up_time"

def test_eval_readme():
    metric = RampUpTimeMetric()
    
    # Test with comprehensive readme
    full_readme = """
    # Model Name
    
    ## Usage
    Here's how to use the model...
    
    ## Installation
    ```bash
    pip install package
    ```
    
    ## Examples
    ```python
    import model
    model.predict()
    ```
    
    Detailed documentation with over 500 characters...
    """ + "a" * 500  # Ensure length > 500
    
    result = metric.eval_readme(full_readme)
    assert result == 1.0  # Should get max score
    
    # Test with partial readme
    partial_readme = """
    # Model Name
    
    ## Usage
    Basic usage instructions
    
    ```python
    import model
    ```
    """
    result = metric.eval_readme(partial_readme)
    assert 0 < result < 1.0  # Should get partial score
    
    # Test with minimal readme
    minimal_readme = "# Model Name"
    result = metric.eval_readme(minimal_readme)
    assert result < 0.5  # Should get low score
    
    # Test with empty/None readme
    assert metric.eval_readme("") == 0.0

def test_eval_model_card():
    metric = RampUpTimeMetric()
    
    # Test with complete metadata
    complete_metadata = {
        "hf_metadata": {
            "description": "Detailed model description",
            "readme_text": "Comprehensive readme",
            "tags": ["tag1", "tag2"]
        }
    }
    result = metric.eval_model_card(complete_metadata)
    assert round(result, 6) == 1.0
    
    # Test with partial metadata
    partial_metadata = {
        "hf_metadata": {
            "description": "Detailed model description",
            "readme_text": "",
            "tags": []
        }
    }
    result = metric.eval_model_card(partial_metadata)
    assert 0 < result < 1.0
    
    # Test with minimal metadata
    minimal_metadata = {
        "hf_metadata": {
            "description": "",
            "readme_text": "",
            "tags": []
        }
    }
    result = metric.eval_model_card(minimal_metadata)
    assert result == 0.0

def test_eval_usage():
    metric = RampUpTimeMetric()
    
    # Test with high usage stats
    high_usage = {
        "hf_metadata": {
            "downloads": 20000,
            "likes": 150,
            "stars": 200
        }
    }
    result = metric.eval_usage(high_usage)
    assert result > 0.8
    
    # Test with moderate usage
    moderate_usage = {
        "hf_metadata": {
            "downloads": 5000,
            "likes": 50,
            "stars": 40
        }
    }
    result = metric.eval_usage(moderate_usage)
    assert 0.3 < result < 0.8
    
    # Test with low usage
    low_usage = {
        "hf_metadata": {
            "downloads": 100,
            "likes": 5,
            "stars": 3
        }
    }
    result = metric.eval_usage(low_usage)
    assert result < 0.3
    
    # Test with missing data
    missing_data = {
        "hf_metadata": {}
    }
    result = metric.eval_usage(missing_data)
    assert result == 0.0

def test_compute():
    metric = RampUpTimeMetric()
    
    # Test successful case
    good_metadata = {
        "hf_metadata": {
            "repo_url": "https://huggingface.co/org/model",
            "description": "Good description",
            "readme_text": """
            # Model
            ## Usage
            Instructions...
            ## Installation
            Steps...
            """ + "a" * 500,
            "downloads": 10000,
            "likes": 100,
            "stars": 80
        }
    }
    result = metric.compute(good_metadata)
    assert isinstance(result.value, float)
    assert 0 <= result.value <= 1.0
    assert result.name == "ramp_up_time"
    assert result.latency_ms >= 0
    
    # Test error case (missing repo_url)
    bad_metadata = {
        "hf_metadata": {}
    }
    result = metric.compute(bad_metadata)
    assert result.value == 0.0
    assert "error" in result.details