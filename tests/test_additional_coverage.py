import os
import json
import time
import logging
from pathlib import Path
import pytest

from src.metric import MetricResult, clamp
from src.entities import HFModel
from src.base import HFModelURL
from src.concurrency import compute_all_metrics
from src import log as slog
from src import ndjson as snd
from src.dataset_quality import DatasetQualityMetric

# metric.clamp tests

def test_clamp_basic():
    assert clamp(0.5) == 0.5
    assert clamp(-1.0) == 0.0
    assert clamp(2.0) == 1.0
    assert clamp(float('nan')) == 0.0

# entities.HFModel tests

def test_hfmodel_name_and_extract_model_name():
    url = "https://huggingface.co/org/model/tree/main/subdir"
    model_url = HFModelURL(url)
    model = HFModel(model_url)

    # name should be last part of repo_id (org/model -> model)
    assert model.name == "model"

    # extract_model_name should return the part before 'tree'
    assert model.extract_model_name() == "model"

    # add_results should populate metric_scores
    r = MetricResult(name="testmetric", value=0.5, details={}, latency_ms=1)
    model.add_results([r])
    assert "testmetric" in model.metric_scores
    assert model.metric_scores["testmetric"].value == 0.5

# concurrency.compute_all_metrics

class DummyMetric:
    def __init__(self, name, delay=0.0):
        self._name = name
        self.delay = delay

    @property
    def name(self):
        return self._name

    def compute(self, metadata):
        if self.delay:
            time.sleep(self.delay)
        return MetricResult(name=self._name, value=1.0, details={})


def test_compute_all_metrics_parallel():
    ctx = {"hf_metadata": {}}
    metrics = [DummyMetric("m1", delay=0.01), DummyMetric("m2", delay=0.02)]
    results = compute_all_metrics(ctx, metrics, max_workers=2) # type: ignore
    assert len(results) == 2
    names = {r.name for r in results}
    assert names == {"m1", "m2"}
    assert all(isinstance(r.latency_ms, int) for r in results)

# log.setup_logging wrappers (writes to file)

def test_setup_logging_writes(monkeypatch, caplog):
    # Set env vars then call setup_logging. We cannot rely on basicConfig
    # to create a file in test runner because logging may already be
    # configured; instead assert that wrapper functions emit log records.
    monkeypatch.setenv("LOG_LEVEL", "1")

    slog.setup_logging()
    with caplog.at_level("INFO"):
        slog.info("Info message for test")
        slog.error("Error message for test")

    texts = "\n".join(r.getMessage() for r in caplog.records)
    assert "Info message for test" in texts
    assert "Error message for test" in texts

# NDJSON encode net_score calculation

def test_ndjson_net_score():
    url = "https://huggingface.co/org/model"
    model = HFModel(HFModelURL(url))

    # Create a few MetricResult entries that are floats
    m1 = MetricResult(name="ramp_up_time", value=0.8, details={}, latency_ms=10)
    m2 = MetricResult(name="license", value=1.0, details={}, latency_ms=5)
    m3 = MetricResult(name="dataset_and_code_score", value=0.5, details={}, latency_ms=2)

    model.metric_scores = {r.name: r for r in [m1, m2, m3]}

    line = snd.NDJSONEncoder.encode(model)
    record = json.loads(line)
    assert "net_score" in record
    assert isinstance(record["net_score"], float)
    # net_score should be rounded and between 0 and 1
    assert 0.0 <= record["net_score"] <= 1.0

# dataset_quality fallback behaviors (monkeypatch fetch_dataset_metadata)

def test_dataset_quality_fallbacks(monkeypatch):
    # Mock fetch_dataset_metadata to provide likes but no downloads and no num_files/size
    def fake_fetch(url):
        return {
            "downloads": 0,
            "likes": 10,
            "num_files": 0,
            "size_mb": 0,
            "readme_text": "short",
            "tags": ["t1", "t2", "t3"],
            "license": ""
        }

    monkeypatch.setattr('src.dataset_quality.fetch_dataset_metadata', fake_fetch)

    metric = DatasetQualityMetric()
    metadata = {"hf_metadata": {"dataset_url": "https://huggingface.co/datasets/x"}}
    result = metric.compute(metadata)

    # downloads should have been set to likes*50
    assert result.details["downloads"] == 10 * 50
    # num_files should fall back to tags length
    assert result.details["num_files"] == 3
    # size_mb should be num_files * 10
    assert result.details["size_mb"] == 30
    assert 0.0 <= result.value <= 1.0 # type: ignore
