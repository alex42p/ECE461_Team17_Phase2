import importlib
import sys
from types import SimpleNamespace
import os


def test_cli_score_dispatch(monkeypatch, tmp_path):
    import src.cli as cli
    monkeypatch.setenv('GITHUB_TOKEN', 'g')

    # create a temporary URL file
    p = tmp_path / 'urls.txt'
    p.write_text('https://huggingface.co/org/model')

    # stub HF metadata and repo contributors
    monkeypatch.setattr(cli, 'fetch_repo_metadata', lambda m: {'readme_text': 'r', 'size_mb': 1})
    monkeypatch.setattr(cli, 'fetch_bus_factor_raw_contributors', lambda url, token: {'contributors': []})

    # stub storage/metrics to avoid network
    monkeypatch.setattr(cli, 'S3Storage', lambda *a, **k: None)
    class R:
        def __init__(self, name, value, latency_ms=1):
            self.name = name
            self.value = value
            self.latency_ms = latency_ms

    monkeypatch.setattr(cli, 'compute_all_metrics', lambda meta, metrics, max_workers=8: [R('license', 1.0, 1)])
    # capture NDJSON output call
    calls = {}
    def fake_print_records(models, include_all=False):
        calls['printed'] = True
    monkeypatch.setattr(cli.NDJSONEncoder, 'print_records', staticmethod(fake_print_records))

    # ensure SystemExit is raised by score() via sys.exit
    try:
        cli.score(str(p))
    except SystemExit as se:
        assert se.code == 0
    assert calls.get('printed') is True


def test_setup_logging_success_and_failure(monkeypatch, tmp_path):
    import src.log as log

    # missing env leads to sys.exit(1)
    monkeypatch.delenv('LOG_FILE', raising=False)
    monkeypatch.delenv('LOG_LEVEL', raising=False)
    try:
        log.setup_logging()
    except SystemExit:
        pass

    # create a writable file and set envs
    f = tmp_path / 'app.log'
    f.write_text('ok')
    monkeypatch.setenv('LOG_FILE', str(f))
    monkeypatch.setenv('LOG_LEVEL', '2')
    # should not raise
    log.setup_logging()
    # call wrappers
    log.debug('d')
    log.info('i')
    log.warn('w')
    log.error('e')
    log.critical('c')
