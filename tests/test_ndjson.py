import json
import pytest
from src.cli_project.io.ndjson import NDJSONEncoder
from src.cli_project.core.entities import HFModel
from src.cli_project.metrics.base import MetricResult
from src.cli_project.urls.base import HFModelURL

def make_model_with_metrics(url: str, results: list[MetricResult] | None = None) -> HFModel:
    model = HFModel(HFModelURL(url))
    if results:
        model.add_results(results)
    return model

def test_encode_empty_model() -> None:
    """Encoding an empty HFModel should only include name + category."""
    model = make_model_with_metrics("https://huggingface.co/google/bert-base-uncased")
    encoded = json.loads(NDJSONEncoder.encode(model))
    assert encoded["name"] == "bert-base-uncased"
    assert encoded["category"] == "MODEL"
    assert "net_score" not in encoded

def test_encode_with_single_metric() -> None:
    """Encoding with one metric should include value + latency + net_score."""
    metric = MetricResult("license", 1.0, {"normalized": "apache-2.0"}, latency_ms=10)
    model = make_model_with_metrics("https://huggingface.co/google/bert-base-uncased", [metric])
    encoded = json.loads(NDJSONEncoder.encode(model))
    assert encoded["license"] == 1.0
    assert encoded["license_latency"] == 10
    assert encoded["net_score"] == pytest.approx(1.0)
    assert encoded["net_score_latency"] == 10

def test_encode_with_multiple_metrics() -> None:
    """Encoding with multiple metrics should compute average net_score + sum latency."""
    metrics = [
        MetricResult("license", 1.0, {}, latency_ms=10),
        MetricResult("bus_factor", 0.5, {}, latency_ms=20),
    ]
    model = make_model_with_metrics("https://huggingface.co/openai/whisper-tiny", metrics)
    encoded = json.loads(NDJSONEncoder.encode(model))
    assert encoded["license"] == 1.0
    assert encoded["bus_factor"] == 0.5
    # average of (1.0 + 0.5) = 0.75
    assert encoded["net_score"] == pytest.approx(0.75, rel=1e-2)
    assert encoded["net_score_latency"] == 30

def test_encode_all_multiple_models() -> None:
    """encode_all should return NDJSON with one line per model."""
    m1 = make_model_with_metrics("https://huggingface.co/org1/model1")
    m2 = make_model_with_metrics("https://huggingface.co/org2/model2")
    ndjson = NDJSONEncoder.encode_all([m1, m2])
    lines = ndjson.strip().splitlines()
    assert len(lines) == 2
    decoded = [json.loads(line) for line in lines]
    assert decoded[0]["name"] == "model1"
    assert decoded[1]["name"] == "model2"

def test_print_records_prints_to_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    """print_records should print full NDJSON to stdout."""
    m: HFModel = make_model_with_metrics("https://huggingface.co/org3/model3")
    NDJSONEncoder.print_records([m])
    captured = capsys.readouterr()
    decoded: dict[str, str] = json.loads(captured.out.strip())
    assert decoded["name"] == "model3"
    assert decoded["category"] == "MODEL"