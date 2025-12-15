from src.ndjson import NDJSONEncoder
from src.entities import HFModel


class DummyResult:
    def __init__(self, name, value, latency_ms=1):
        self.name = name
        self.value = value
        self.latency_ms = latency_ms


def make_model(name="m", category="model", metrics=None):
    model_url = type('U', (), {'url': 'https://huggingface.co/org/model', 'category': category})
    m = HFModel(model_url=model_url)
    m.metric_scores = metrics or {}
    return m


def test_encode_and_encode_all_and_phase_one():
    # basic metrics without net_score field -> net_score computed
    metrics = {
        'ramp_up_time': DummyResult('ramp_up_time', 1.0, 2),
        'license': DummyResult('license', 1.0, 3),
    }
    m = make_model(metrics=metrics)
    line = NDJSONEncoder.encode(m)
    assert 'net_score' in line

    # phase_one excludes phase2-only metrics
    metrics2 = {
        'ramp_up_time': DummyResult('ramp_up_time', 0.5, 1),
        'reviewedness': DummyResult('reviewedness', 0.0, 1),
    }
    m2 = make_model(metrics=metrics2)
    out = NDJSONEncoder.encode_all([m, m2], phase_one=True)
    assert '\n' in out


def test_print_records(capsys):
    m = make_model(metrics={'ramp_up_time': DummyResult('ramp_up_time', 0.1, 1)})
    NDJSONEncoder.print_records([m])
    captured = capsys.readouterr()
    assert 'ramp_up_time' in captured.out
