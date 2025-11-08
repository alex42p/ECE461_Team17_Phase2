import pytest
from src.reviewedness import ReviewednessMetric


def test_reviewedness_metric_init():
    metric = ReviewednessMetric(github_token="fake_token")
    assert metric.name == "reviewedness"
    assert metric.github_token == "fake_token"


def test_parse_github_url():
    metric = ReviewednessMetric()
    
    owner, repo = metric._parse_github_url("https://github.com/openai/whisper")
    assert owner == "openai"
    assert repo == "whisper"
    
    owner, repo = metric._parse_github_url("https://github.com/google/bert/")
    assert owner == "google"
    assert repo == "bert"


def test_compute_no_repo():
    metric = ReviewednessMetric(github_token="fake")
    
    metadata = {
        "repo_metadata": {}
    }
    
    result = metric.compute(metadata)
    assert result.value == -1.0
    assert "No linked GitHub repository" in result.details["reason"]


def test_compute_with_pr_stats(monkeypatch):
    """Test with mocked GitHub API response."""
    metric = ReviewednessMetric(github_token="fake")
    
    # Mock PR stats
    def mock_fetch_pr_stats(owner, repo):
        return 80, 100  # 80 commits via PR, 100 total
    
    monkeypatch.setattr(metric, "_fetch_pr_stats", mock_fetch_pr_stats)
    
    metadata = {
        "repo_metadata": {
            "repo_url": "https://github.com/test/repo"
        }
    }
    
    result = metric.compute(metadata)
    assert result.value == 0.8
    assert result.details["pr_commits"] == 80
    assert result.details["total_commits"] == 100
    assert result.details["review_percentage"] == 80.0
