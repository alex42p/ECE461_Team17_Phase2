import pytest
from src.performance_claims import PerformanceClaimsMetric

def test_performance_claims_metric_init():
    metric = PerformanceClaimsMetric()
    assert metric.name == "performance_claims"

def test_eval_readme():
    metric = PerformanceClaimsMetric()
    
    # Test with performance indicators and numerical results
    good_readme = """
    # Model Performance
    
    Our model achieves 95.2% accuracy on the benchmark dataset.
    F1 score: 0.87
    BLEU score: 42.5
    
    ## Evaluation Results
    | Metric | Value |
    |--------|-------|
    | Accuracy | 94.3% |
    | Perplexity | 12.5 |
    """
    score = metric.eval_readme(good_readme)
    assert score > 0.8  # Should get high score
    
    # Test with just performance indicators, no numbers
    partial_readme = """
    # Model Performance
    
    This model performs well on benchmark evaluations.
    We evaluated accuracy and F1 score.
    """
    score = metric.eval_readme(partial_readme)
    assert 0.2 < score < 0.8  # Should get partial score
    
    # Test with no performance indicators
    bad_readme = """
    # Model
    
    This is a language model.
    """
    score = metric.eval_readme(bad_readme)
    assert score < 0.2  # Should get low score
    
    # Test with empty readme
    assert metric.eval_readme("") == 0.0

def test_eval_siblings():
    metric = PerformanceClaimsMetric()
    
    # Test with evaluation files
    good_siblings = {
        "siblings": [
            {"rfilename": "evaluate.py"},
            {"rfilename": "benchmark_results.txt"},
            {"rfilename": "test_metrics.py"}
        ]
    }
    assert metric.eval_siblings(good_siblings) == 1.0
    
    # Test with no evaluation files
    bad_siblings = {
        "siblings": [
            {"rfilename": "model.py"},
            {"rfilename": "utils.py"},
            {"rfilename": "README.md"}
        ]
    }
    assert metric.eval_siblings(bad_siblings) == 0.2
    
    # Test with empty/invalid siblings
    assert metric.eval_siblings({}) == 0.0
    assert metric.eval_siblings({"siblings": []}) == 0.0
    assert metric.eval_siblings({"siblings": None}) == 0.0

def test_compute():
    metric = PerformanceClaimsMetric()
    
    # Test with good performance data
    good_metadata = {
        "hf_metadata": {
            "readme_text": """
            # Performance
            Accuracy: 95.2%
            F1 Score: 0.89
            """,
            "siblings": [
                {"rfilename": "evaluate.py"},
                {"rfilename": "metrics.py"}
            ]
        }
    }
    result = metric.compute(good_metadata)
    assert isinstance(result.value, float)
    assert 0.7 < result.value <= 1.0
    assert result.name == "performance_claims"
    assert result.details["success"] is True
    assert result.latency_ms >= 0
    
    # Test with minimal performance data
    minimal_metadata = {
        "hf_metadata": {
            "readme_text": "Basic model description",
            "siblings": []
        }
    }
    result = metric.compute(minimal_metadata)
    assert result.value < 0.3 # type: ignore
    assert result.details["success"] is True
    
    # Test with empty metadata
    empty_metadata = {
        "hf_metadata": {}
    }
    result = metric.compute(empty_metadata)
    assert result.value == 0.0
    assert result.details["success"] is True