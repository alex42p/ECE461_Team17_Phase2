import importlib
import src.cli as cli


def test_cli_score_net_score_all_metrics(monkeypatch, tmp_path):
    importlib.reload(cli)

    # create URL file
    p = tmp_path / 'urls.txt'
    # parse_url_file expects lines with three comma-separated fields: code,dataset,model
    p.write_text(',,https://huggingface.co/org/model')

    # stub HF metadata and repo contributors
    monkeypatch.setattr(cli, 'fetch_repo_metadata', lambda m: {'readme_text': 'r', 'size_mb': 10})
    monkeypatch.setattr(cli, 'fetch_bus_factor_raw_contributors', lambda url, token: {'contributors': []})

    # define fake metric result objects for many metrics including size_score dict
    class R:
        def __init__(self, name, value, latency_ms=1):
            self.name = name
            self.value = value
            self.latency_ms = latency_ms

    fake_results = [
        R('ramp_up_time', 0.5, 1),
        R('license', 1.0, 1),
        R('performance_claims', 0.2, 1),
        R('bus_factor', 0.1, 1),
        R('code_quality', 0.3, 1),
        R('dataset_quality', 0.4, 1),
        R('dataset_and_code_score', 0.2, 1),
        R('size_score', {'raspberry_pi': 1.0, 'jetson_nano': 0.8, 'desktop_pc': 0.6, 'aws_server': 0.7}, 1),
        R('reproducibility', 0.1, 1),
        R('reviewedness', 0.0, 1),
        R('tree_score', 0.05, 1),
    ]

    # ensure compute_all_metrics returns our fake_results regardless of passed metrics
    monkeypatch.setattr(cli, 'compute_all_metrics', lambda meta, metrics, max_workers=8: fake_results)

    printed = {'ok': False}
    def fake_print(records):
        printed['ok'] = True
    monkeypatch.setattr(cli.NDJSONEncoder, 'print_records', staticmethod(fake_print))

    # run score - should exit with 0
    try:
        cli.score(str(p))
    except SystemExit as se:
        assert se.code == 0
    assert printed['ok'] is True


def test_cli_metric_injection(monkeypatch, tmp_path):
    import importlib
    import src.cli as cli_mod
    import src.tree_score as ts
    import src.reviewedness as rv

    importlib.reload(cli_mod)

    p = tmp_path / 'urls2.txt'
    p.write_text(',,https://huggingface.co/org/model')

    # Ensure model has a code repo so repo metadata path is taken
    monkeypatch.setattr(cli_mod, 'fetch_repo_metadata', lambda m: {'readme_text': 'r', 'size_mb': 1})
    monkeypatch.setattr(cli_mod, 'fetch_bus_factor_raw_contributors', lambda url, token: {'contributors': []})

    # Create fake subclasses of real metric classes to test injection
    class FakeTree(ts.TreeScoreMetric):
        def __init__(self):
            super().__init__()

    class FakeReviewed(rv.ReviewednessMetric):
        def __init__(self):
            super().__init__()

    # Replace Metric in the cli module with a stand-in that returns our fake classes
    FakeMetricHolder = type('M', (), {'__subclasses__': staticmethod(lambda: [FakeTree, FakeReviewed])})
    monkeypatch.setattr(cli_mod, 'Metric', FakeMetricHolder)

    captured = {}
    def fake_compute_all_metrics(meta, metrics, max_workers=8):
        # verify injections happened
        assert isinstance(metrics[0], FakeTree)
        assert hasattr(metrics[0], 'storage')
        assert isinstance(metrics[1], FakeReviewed)
        assert hasattr(metrics[1], 'github_token')
        captured['ok'] = True
        return []

    monkeypatch.setattr(cli_mod, 'compute_all_metrics', fake_compute_all_metrics)
    # stub S3Storage to avoid creating real clients
    monkeypatch.setattr(cli_mod, 'S3Storage', lambda *a, **k: object())
    # sanity check: ensure Metric.__subclasses__ returns our classes
    assert cli_mod.Metric.__subclasses__() == [FakeTree, FakeReviewed]
    # stub NDJSON print
    monkeypatch.setattr(cli_mod.NDJSONEncoder, 'print_records', staticmethod(lambda models: None))

    try:
        cli_mod.score(str(p))
    except SystemExit as se:
        assert se.code == 0
    assert captured.get('ok') is True


def test_install_and_test_and_main(monkeypatch, capsys):
    import importlib
    import src.cli as cli
    importlib.reload(cli)

    # install should exit with subprocess returncode
    monkeypatch.setattr(cli, 'subprocess', type('S', (), {'run': staticmethod(lambda *a, **k: type('R', (), {'returncode': 5})())}))
    try:
        cli.install()
    except SystemExit as se:
        assert se.code == 5

    # test() should call tester.run_tests and exit with that code
    monkeypatch.setattr(cli, 'tester', type('T', (), {'run_tests': staticmethod(lambda : 0)}))
    monkeypatch.setattr(cli.log, 'setup_logging', lambda : None)
    try:
        cli.test()
    except SystemExit as se:
        assert se.code == 0

    # main with no args should print help (sys.argv=['run'])
    import sys
    monkeypatch.setattr(sys, 'argv', ['run'])
    cli.main()
    captured = capsys.readouterr()
    assert 'usage' in captured.out.lower()
