import pytest
from pathlib import Path
from typing import Any, Dict
from src.cli_project.metrics.code_quality import CodeQualityMetric
from src.cli_project.metrics.dataset_quality import DatasetQualityMetric
from src.cli_project.metrics.dataset_and_code import DatasetAndCodeMetric
from src.cli_project.metrics.base import MetricResult

# ----------------------------
# Fake metadata (matches your CLI structure)
# ----------------------------
FAKE_METADATA: Dict[str, Any] = {
    "hf_metadata": {"repo_id": "fake-user/fake-model", "dataset_url": "https://huggingface.co/datasets/bookcorpus/bookcorpus"},
    "repo_metadata": {"repo_url": "https://github.com/fake-user/fake-model"},
    "nof_code_ds": {"nof_code": 1, "nof_ds": 1},
}

# ----------------------------
# Code Quality Metric
# ----------------------------
@pytest.mark.integration
def test_code_quality_metric_real() -> None:
    """Integration test: run CodeQualityMetric on a real Hugging Face model repo."""
    metadata = {
        "hf_metadata": {"repo_id": "bert-base-uncased"},  # official HF repo
        "repo_metadata": {"repo_url": "https://github.com/google-research/bert"},
        "nof_code_ds": {"nof_code": 1, "nof_ds": 0},
    }

    metric = CodeQualityMetric()
    result: MetricResult = metric.compute(metadata)

    assert isinstance(result, MetricResult)
    assert result.name == "code_quality"
    assert 0.0 <= float(result.value) <= 1.0
    # At least some components should be > 0
    assert any(v > 0 for v in result.details.values())

# ----------------------------
# Dataset Quality Metric
# ----------------------------
def test_dataset_quality_metric_runs() -> None:
    metric: DatasetQualityMetric = DatasetQualityMetric()
    result: MetricResult = metric.compute(FAKE_METADATA)

    assert isinstance(result, MetricResult)
    # Some implementations use "dataset_quality", some "dataset_quality_score"
    assert result.name in {"dataset_quality", "dataset_quality_score"}
    assert isinstance(result.details, dict)
    assert isinstance(result.value, (float, dict))

# ----------------------------
# Dataset + Code Metric
# ----------------------------
def test_dataset_and_code_metric_runs() -> None:
    metric: DatasetAndCodeMetric = DatasetAndCodeMetric()
    result: MetricResult = metric.compute(FAKE_METADATA)

    assert isinstance(result, MetricResult)
    # Accept either "dataset_and_code" or "dataset_and_code_score"
    assert result.name in {"dataset_and_code", "dataset_and_code_score"}
    assert isinstance(result.details, dict)
    assert "nof_code" in FAKE_METADATA["nof_code_ds"]
    assert "nof_ds" in FAKE_METADATA["nof_code_ds"]
