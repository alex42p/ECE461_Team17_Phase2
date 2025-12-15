import importlib
import os
import tempfile
import src.metric as metric
import src.performance_claims as pc
import src.log as logmod


def test_clamp_behaviour():
    assert metric.clamp(float('nan')) == 0.0
    assert metric.clamp(-1.0) == 0.0
    assert metric.clamp(2.0) == 1.0
    assert metric.clamp(0.5) == 0.5


def test_performance_claims_readme_and_siblings():
    m = pc.PerformanceClaimsMetric()
    # empty readme
    assert m.eval_readme('') == 0.0
    # readme mentioning accuracy with number
    assert m.eval_readme('This model has accuracy 0.92 on test') > 0.0
    # siblings file detection
    assert m.eval_siblings({'siblings': [{'rfilename': 'eval_results.json'}]}) == 1.0
    assert m.eval_siblings({'siblings': [{'rfilename': 'README.md'}]}) == 0.2


def test_setup_logging_paths(tmp_path, monkeypatch):
    # missing env -> exits
    monkeypatch.delenv('LOG_FILE', raising=False)
    monkeypatch.delenv('LOG_LEVEL', raising=False)
    try:
        logmod.setup_logging()
    except SystemExit as se:
        assert se.code == 1

    # valid file and level
    f = tmp_path / 'app.log'
    f.write_text('')
    monkeypatch.setenv('LOG_FILE', str(f))
    monkeypatch.setenv('LOG_LEVEL', '2')
    # Should not raise
    logmod.setup_logging()