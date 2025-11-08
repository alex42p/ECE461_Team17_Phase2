import pytest
from src.tree_score import TreeScoreMetric


def test_tree_score_metric_init():
    metric = TreeScoreMetric()
    assert metric.name == "tree_score"


def test_compute_no_parents():
    metric = TreeScoreMetric()
    
    metadata = {
        "hf_metadata": {
            "siblings": [],
            "readme_text": "# Model\n\nNo parents mentioned."
        }
    }
    
    result = metric.compute(metadata)
    assert result.value == 0.0
    assert "No parent models found" in result.details["reason"]


def test_extract_parent_models():
    metric = TreeScoreMetric()
    
    metadata = {
        "hf_metadata": {
            "siblings": [{"rfilename": "config.json"}],
            "readme_text": """
            # Model
            
            This model was fine-tuned from bert-base-uncased.
            It builds on google/bert-large.
            """
        }
    }
    
    parents = metric._extract_parent_models(metadata)
    assert len(parents) >= 1
    assert any("bert" in p.lower() for p in parents)


def test_compute_with_parents(monkeypatch):
    """Test with mocked parent score lookup."""
    metric = TreeScoreMetric()
    
    # Mock storage
    class MockStorage:
        def search_by_regex(self, pattern):
            return [{
                "id": "parent-1",
                "scores": {"net_score": {"value": 0.9}}
            }]
    
    metric.storage = MockStorage()
    
    # Mock parent extraction
    def mock_extract(metadata):
        return ["parent-1"]
    
    monkeypatch.setattr(metric, "_extract_parent_models", mock_extract)
    
    metadata = {
        "artifact_id": "child-1",
        "hf_metadata": {
            "siblings": [],
            "readme_text": ""
        }
    }
    
    result = metric.compute(metadata)
    assert result.value == 0.9
    assert result.details["num_parents"] == 1
    assert result.details["evaluated_parents"] == 1