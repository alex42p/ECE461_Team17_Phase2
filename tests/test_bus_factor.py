import pytest
from datetime import datetime, timezone, timedelta
from src.bus_factor import BusFactorMetric

def test_bus_factor_metric_init():
    metric = BusFactorMetric()
    assert metric.name == "bus_factor"

def test_eval_contributors():
    metric = BusFactorMetric()
    
    # Test various contributor counts
    test_cases = [
        (0, 0.2),    # No contributors
        (2, 0.2),    # Very few contributors
        (3, 0.5),    # Small team
        (6, 0.7),    # Medium team
        (10, 1.0),   # Large team
        (15, 1.0),   # Very large team
        (None, 0.2), # Missing data
    ]
    
    for count, expected_score in test_cases:
        result = metric._eval_contributors({"unique_committers_count": count})
        assert result == expected_score

def test_eval_organization():
    metric = BusFactorMetric()
    
    # Test known organizations
    known_orgs = [
        {"author": "Google AI", "repo_id": "google/bert"},
        {"author": "Microsoft Research", "repo_id": "microsoft/model"},
        {"author": "Facebook AI", "repo_id": "meta/llama"},
        {"author": "OpenAI", "repo_id": "openai/gpt"},
        {"author": "DeepMind", "repo_id": "deepmind/model"}
    ]
    for metadata in known_orgs:
        assert metric._eval_organization(metadata) == 1.0

    # Test organization indicators
    org_indicators = [
        {"author": "AI Research Team", "repo_id": "some-model"},
        {"author": "ML Lab", "repo_id": "model"},
        {"author": "Institute Corp", "repo_id": "model"},
        {"author": "AI Institute", "repo_id": "model"}
    ]
    for metadata in org_indicators:
        assert metric._eval_organization(metadata) == 0.8

    # Test individual authors
    individuals = [
        {"author": "John Doe", "repo_id": "model"},
        {"author": "", "repo_id": "model"}
    ]
    for metadata in individuals:
        assert metric._eval_organization(metadata) == 0.3

def test_eval_activity():
    metric = BusFactorMetric()
    now = datetime.now(timezone.utc)
    
    # Test various last modified dates
    test_cases = [
        (now - timedelta(days=15), 1.0),    # Very recent
        (now - timedelta(days=45), 0.7),    # Recent
        (now - timedelta(days=180), 0.4),   # Somewhat old
        (now - timedelta(days=400), 0.1),   # Old
        (None, 0.2),                        # Missing date
    ]
    
    for date, expected_score in test_cases:
        if date:
            last_modified = date.isoformat()
        else:
            last_modified = None
        result = metric._eval_activity({"lastModified": last_modified})
        assert result == expected_score

def test_compute():
    metric = BusFactorMetric()
    
    # Test case with good indicators
    good_case = {
        "hf_metadata": {
            "author": "Google Research",
            "repo_id": "google/bert",
            "lastModified": datetime.now(timezone.utc).isoformat()
        },
        "repo_metadata": {
            "unique_committers_count": 15
        }
    }
    result = metric.compute(good_case)
    assert result.value > 0.8  # type: ignore
    assert result.name == "bus_factor"
    assert result.details["success"] is True
    assert result.latency_ms >= 0

    # Test case with poor indicators
    poor_case = {
        "hf_metadata": {
            "author": "John Doe",
            "repo_id": "johndoe/model",
            "lastModified": (datetime.now(timezone.utc) - timedelta(days=500)).isoformat()
        },
        "repo_metadata": {
            "unique_committers_count": 1
        }
    }
    result = metric.compute(poor_case)
    assert result.value < 0.5  # type: ignore
    assert result.details["success"] is True