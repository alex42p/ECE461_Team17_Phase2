import pytest
from typing import Any
from src.license import LicenseMetric
from src.bus_factor import BusFactorMetric
from src.ramp_up_time import RampUpTimeMetric
from src.performance_claims import PerformanceClaimsMetric
from src.size_score import SizeScoreMetric
from src.metric import MetricResult
from src import git_repo
from src.huggingface import fetch_repo_metadata
from src.base import HFModelURL, CodeRepoURL
from src.entities import HFModel
from src.git_repo import fetch_bus_factor_raw_contributors

LICENSE_CASES = [
    ("MIT", "mit", 1.0),
    ("Apache License 2.0", "apache-2.0", 1.0),
    ("BSD-3", "bsd-3-clause", 1.0),
    ("BSD 3", "bsd-3-clause", 1.0),
    ("BSD-2", "bsd-2-clause", 1.0),
    ("BSD 2", "bsd-2-clause", 1.0),
    ("BSD", "bsd", 1.0),
    ("LGPL 2.1", "lgpl-2.1", 1.0),
    ("LGPL 3.0", "lgpl-3.0", 1.0),
    ("weird-custom-license", "weird-custom-license", 0.0),
]

@pytest.mark.parametrize("license_str, expected_norm, expected_value", LICENSE_CASES)
def test_license_metric_all(license_str, expected_norm, expected_value):
    metadata = {"hf_metadata": {"license": license_str}}
    metric = LicenseMetric()
    result = metric.compute(metadata)
    assert isinstance(result, MetricResult)
    assert result.name == "license"
    assert result.value == expected_value
    assert result.details["normalized"] == expected_norm


def test_license_metric_missing_license():
    """If license is missing entirely, metric should return 0.0 with error detail."""
    metadata = {"hf_metadata": {}}
    metric = LicenseMetric()
    result = metric.compute(metadata)
    assert result.value == 0.0
    assert "error" in result.details


@pytest.mark.parametrize("raw, expected", [
    ("", None),
    (None, None),
])
def test_norm_empty_and_none(raw, expected):
    assert _norm(raw) == expected

def test_license_metric() -> None:
    metadata = {"hf_metadata": {"license": "apache-2.0"}}
    metric = LicenseMetric()
    result = metric.compute(metadata)
    assert isinstance(result, MetricResult)
    assert result.name == "license"
    assert result.value in (0.0, 1.0)
    assert "license" in result.details

def test_license_metric_unrecognized() -> None:
    metadata = {"hf_metadata": {"license": "weird-custom-license"}}
    metric = LicenseMetric()
    result = metric.compute(metadata)
    assert result.value == 0.0
    assert result.details["normalized"] == "weird-custom-license"


def test_bus_factor_metric() -> None:
    metadata = {"repo_metadata": {"recent_committers": 5}}
    metric = BusFactorMetric()
    result = metric.compute(metadata)
    assert isinstance(result, MetricResult)
    assert result.name == "bus_factor"
    assert 0.0 <= result.value <= 1.0
    assert result.details["recent_committers"] == 5

def test_bus_factor_metric_zero_committers() -> None:
    metadata = {"repo_metadata": {"recent_committers": 0}}
    metric = BusFactorMetric()
    result = metric.compute(metadata)
    assert result.value == 0.0
    assert result.details["recent_committers"] == 0


def test_ramp_up_time_metric() -> None:
    metadata = {"hf_metadata": {"repo_url": "https://huggingface.co/google-bert/bert-base-uncased"}}
    metric = RampUpTimeMetric()
    result = metric.compute(metadata)
    assert isinstance(result, MetricResult)
    assert result.name == "ramp_up_time"
    assert 0.0 <= result.value <= 1.0
    assert isinstance(result.details, dict)

def test_ramp_up_time_metric_missing_url() -> None:
    metadata = {"hf_metadata":  {"repo_url": {}}}
    metric = RampUpTimeMetric()
    result = metric.compute(metadata)
    assert result.value == 0.0
    assert "repo_url" not in result.details or result.details.get("repo_url") is None


def test_performance_claims_metric() -> None:
    metadata = {"hf_metadata": {"repo_url": "https://huggingface.co/google-bert/bert-base-uncased"}}
    metric = PerformanceClaimsMetric()
    result = metric.compute(metadata)
    assert isinstance(result, MetricResult)
    assert result.name == "performance_claims"
    assert 0.0 <= result.value <= 1.0
    assert isinstance(result.details, dict)

def test_performance_claims_metric_missing_url() -> None:
    metadata = {"hf_metadata":  {"repo_url": {}}}
    metric = PerformanceClaimsMetric()
    result = metric.compute(metadata)
    assert result.value == 0.0
    assert isinstance(result.details, dict)


# --------------------------
# SizeScoreMetric tests
# --------------------------

def test_size_score_metric_inside_range() -> None:
    metadata = {"hf_metadata": {"size_mb": 120}}  # inside Pi sweet spot (50–200)
    metric = SizeScoreMetric()
    result = metric.compute(metadata)
    assert result.value["raspberry_pi"] == 1.0
    assert result.details["size_mb"] == 120

def test_size_score_metric_smaller_than_range() -> None:
    metadata = {"hf_metadata": {"size_mb": 30}}  # smaller than Pi min (50)
    metric = SizeScoreMetric()
    result = metric.compute(metadata)
    assert result.value["raspberry_pi"] == pytest.approx(0.6, rel=1e-3)

def test_size_score_metric_larger_than_range() -> None:
    metadata = {"hf_metadata": {"size_mb": 6000}}  # larger than AWS max (5000)
    metric = SizeScoreMetric()
    result = metric.compute(metadata)
    assert 0.0 < result.value["aws_server"] < 1.0
    assert result.value["aws_server"] == pytest.approx(5000 / 6000, rel=1e-3)


def test_fetch_repo_metadata_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pipeline: HFModelURL → HFModel → fetch_repo_metadata."""

    class FakeHFResponse:
        status_code: int = 200
        def json(self) -> dict[str, Any]:
            return {"modelId": "bert-base-uncased", "license": "apache-2.0", "sha": "123abc"}

    monkeypatch.setattr("cli_project.adapters.huggingface.requests.get", lambda *a, **k: FakeHFResponse())

    u = HFModelURL("https://huggingface.co/google-bert/bert-base-uncased")
    model = HFModel(model_url=u)

    hf_metadata = fetch_repo_metadata(model)

    assert isinstance(hf_metadata, dict)
    assert hf_metadata["license"] == "apache-2.0"


def test_fetch_bus_factor_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pipeline: HFModelURL.code[0].url → fetch_bus_factor_raw_contributors."""

    class FakeContribResponse:
        status_code: int = 200
        def __init__(self, data: list[dict[str, Any]]) -> None:
            self._data = data
        def json(self) -> list[dict[str, Any]]:
            return self._data

    class FakeRepoResponse:
        status_code: int = 200
        def json(self) -> dict[str, Any]:
            return {"pushed_at": "2024-01-01T00:00:00Z"}

    responses: list[Any] = [
        FakeContribResponse([{"login": "alice", "contributions": 5}, {"login": "bob", "contributions": 3}]),
        FakeContribResponse([]),  # end of contributors
        FakeRepoResponse(),       # repo API
    ]

    def fake_get(*a: Any, **k: Any) -> Any:
        return responses.pop(0)

    monkeypatch.setattr("cli_project.adapters.git_repo.requests.get", fake_get)

    u = HFModelURL("https://huggingface.co/fake/model-with-repo",
                   code=[CodeRepoURL("https://github.com/fake/repo")])
    model = HFModel(model_url=u)

    repo_metadata = fetch_bus_factor_raw_contributors(model.model_url.code[0].url, token="fake-token")

    assert isinstance(repo_metadata, dict)
    assert repo_metadata["unique_committers_count"] == 2
    assert "last_commit_date" in repo_metadata


def test_pipeline_end_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pipeline: HFModelURL → HFModel → fetch_repo_metadata + fetch_bus_factor."""

    # --- Fake Hugging Face ---
    class FakeHFResponse:
        status_code: int = 200
        def json(self) -> dict[str, Any]:
            return {"modelId": "bert", "license": "mit", "sha": "xyz"}

    monkeypatch.setattr("cli_project.adapters.huggingface.requests.get", lambda *a, **k: FakeHFResponse())

    # --- Fake GitHub ---
    class FakeContribResponse:
        status_code: int = 200
        def __init__(self, data: list[dict[str, Any]]) -> None:
            self._data = data
        def json(self) -> list[dict[str, Any]]:
            return self._data

    class FakeRepoResponse:
        status_code: int = 200
        def json(self) -> dict[str, Any]:
            return {"pushed_at": "2024-01-01T00:00:00Z"}

    responses: list[Any] = [
        FakeContribResponse([{"login": "dev", "contributions": 10}]),
        FakeContribResponse([]),
        FakeRepoResponse(),
    ]

    def fake_get(*a: Any, **k: Any) -> Any:
        return responses.pop(0)

    monkeypatch.setattr("cli_project.adapters.git_repo.requests.get", fake_get)

    # --- HFModel with repo ---
    u = HFModelURL("https://huggingface.co/fake/bert", code=[CodeRepoURL("https://github.com/fake/repo")])
    model = HFModel(model_url=u)

    hf_metadata = fetch_repo_metadata(model)
    assert hf_metadata["license"] == "mit"

    repo_metadata = fetch_bus_factor_raw_contributors(model.model_url.code[0].url)

    assert "unique_committers_count" in repo_metadata
    assert "last_commit_date" in repo_metadata