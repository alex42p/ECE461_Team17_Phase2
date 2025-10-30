import pytest
from src.dataset_and_code import DatasetAndCodeMetric

def test_dataset_and_code_metric_init():
    metric = DatasetAndCodeMetric()
    assert metric.name == "dataset_and_code_score"
    assert hasattr(metric, "_DATASET_KEYWORDS")
    assert hasattr(metric, "_CODE_KEYWORDS")

def test_contains_keywords():
    metric = DatasetAndCodeMetric()
    
    # Test dataset keyword detection
    text_with_dataset = """
    This model was trained on a large dataset.
    We used the training data from xyz corpus.
    The evaluation data shows good results.
    """
    assert metric._contains_keywords(text_with_dataset, metric._DATASET_KEYWORDS)
    
    # Test code keyword detection
    text_with_code = """
    ## Examples
    Here's how to use the model:
    ```python
    model.predict()
    ```
    Check the notebook for more examples.
    """
    assert metric._contains_keywords(text_with_code, metric._CODE_KEYWORDS)
    
    # Test text without keywords
    text_without_keywords = """
    This is a basic description.
    Nothing special here.
    """
    assert not metric._contains_keywords(text_without_keywords, metric._DATASET_KEYWORDS)
    assert not metric._contains_keywords(text_without_keywords, metric._CODE_KEYWORDS)
    
    # Test empty text
    assert not metric._contains_keywords("", metric._DATASET_KEYWORDS)

def test_compute():
    metric = DatasetAndCodeMetric()
    
    # Test with both dataset and code present
    good_metadata = {
        "nof_code_ds": {
            "nof_ds": 1,
            "nof_code": 1
        },
        "readme_text": """
        # Model
        
        Trained on a large dataset.
        
        ## Examples
        ```python
        model.predict()
        ```
        """
    }
    result = metric.compute(good_metadata)
    assert result.value == 1.0  # Both signals present
    assert result.name == "dataset_and_code_score"
    assert result.details["dataset_present"] is True
    assert result.details["code_present"] is True
    assert result.latency_ms >= 0
    
    # Test with only dataset present
    dataset_only_metadata = {
        "nof_code_ds": {
            "nof_ds": 1,
            "nof_code": 0
        },
        "readme_text": "Trained on xyz dataset."
    }
    result = metric.compute(dataset_only_metadata)
    assert result.value == 0.5  # Only dataset signal
    
    # Test with only code present
    code_only_metadata = {
        "nof_code_ds": {
            "nof_ds": 0,
            "nof_code": 1
        },
        "readme_text": """
        ## Examples
        ```python
        model.predict()
        ```
        """
    }
    result = metric.compute(code_only_metadata)
    assert result.value == 0.5  # Only code signal
    
    # Test with neither present
    empty_metadata = {
        "nof_code_ds": {
            "nof_ds": 0,
            "nof_code": 0
        },
        "readme_text": "Basic description"
    }
    result = metric.compute(empty_metadata)
    assert result.value == 0.0  # No signals present

def test_compute_with_missing_data():
    metric = DatasetAndCodeMetric()
    
    # Test with missing nof_code_ds
    missing_metadata = {
        "readme_text": "Some text"
    }
    with pytest.raises(KeyError):
        metric.compute(missing_metadata)
    
    # Test with missing readme_text but has nof_code_ds
    partial_metadata = {
        "nof_code_ds": {
            "nof_ds": 1,
            "nof_code": 1
        }
    }
    result = metric.compute(partial_metadata)
    assert isinstance(result.value, float)
    assert 0 <= result.value <= 1.0