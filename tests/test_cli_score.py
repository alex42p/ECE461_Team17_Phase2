import importlib
from types import SimpleNamespace
from pathlib import Path
import pytest

import src.base as base
from src.metric import MetricResult


def test_score_flow(monkeypatch, tmp_path):
    # Set GITHUB_TOKEN before importing cli module (it checks at import time)
    monkeypatch.setenv('GITHUB_TOKEN', 'fake')
    import importlib
    import src.cli as cli
    importlib.reload(cli)

    # Prepare two HFModelURL objects, one with code and dataset, one without
    model1 = base.HFModelURL("https://huggingface.co/org/model1", datasets=[base.HFDatasetURL("https://huggingface.co/datasets/ds1")], code=[base.CodeRepoURL("https://github.com/org/repo1")])
    model2 = base.HFModelURL("https://huggingface.co/org/model2")

    # Monkeypatch parse_url_file to return our models
    monkeypatch.setattr(cli, "parse_url_file", lambda path: [model1, model2])

    # Monkeypatch fetch_repo_metadata to set model.metadata and return hf metadata
    def fake_fetch_repo_metadata(model):
        return {"repo_url": model.model_url.url, "repo_id": model.model_url.url.strip('/').split('/')[-1], "likes": 10}
    monkeypatch.setattr(cli, "fetch_repo_metadata", fake_fetch_repo_metadata)

    # Monkeypatch git repo fetch
    monkeypatch.setattr(cli, "fetch_bus_factor_raw_contributors", lambda repo_url, token: {"unique_committers_count": 5})

    # Monkeypatch NDJSONEncoder.print_records to capture the models param
    recorded = {}
    def fake_print_records(models):
        recorded['models'] = models
    monkeypatch.setattr(cli.NDJSONEncoder, "print_records", staticmethod(fake_print_records))

    # Monkeypatch compute_all_metrics to return one MetricResult per call
    def fake_compute_all_metrics(metadata, metrics, max_workers=None):
        return [MetricResult(name="dummy", value=0.5, details={}, latency_ms=1)]
    monkeypatch.setattr(cli, "compute_all_metrics", fake_compute_all_metrics)

    # Call score and catch SystemExit
    with pytest.raises(SystemExit) as se:
        cli.score(str(tmp_path / "urls.txt"))
    assert se.value.code == 0

    # Check that NDJSONEncoder.print_records was called and models were recorded
    assert 'models' in recorded
    assert len(recorded['models']) == 2
    # Verify that the first model has metric_scores populated
    assert recorded['models'][0].metric_scores
