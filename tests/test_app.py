import importlib
import json
from decimal import Decimal

import pytest


def reload_app_with_env(monkeypatch):
    # Ensure import-time secrets manager code doesn't run
    envs = {
        "AWS_ACCESS_KEY_ID": "AKIAFAKE",
        "AWS_SECRET_ACCESS_KEY": "SECRET",
        "AWS_DEFAULT_REGION": "us-east-1",
        "FLASK_SECRET_KEY": "flasksecret",
        "GITHUB_TOKEN": "gh123",
        "HF_TOKEN": "hf123",
        "S3_BUCKET_NAME": "bucket"
    }
    for k, v in envs.items():
        monkeypatch.setenv(k, v)

    # Prevent actual AWS clients from being created during import by stubbing boto3
    import boto3
    class _DummyTable:
        def __init__(self):
            self.table_name = 'dummy'
            self.table_status = 'ACTIVE'
            self._items = {}
        def put_item(self, Item):
            self._items[Item.get('id')] = Item
        def get_item(self, Key):
            item = self._items.get(Key.get('id'))
            return {'Item': item} if item else {}
        def scan(self):
            return {'Items': list(self._items.values())}
        def update_item(self, **kwargs):
            key = kwargs['Key']['id']
            attrs = kwargs.get('ExpressionAttributeValues', {})
            # naive update for testing
            if key in self._items:
                self._items[key].update(attrs)
                return {'Attributes': self._items[key]}
            return {'Attributes': {}}
        def delete_item(self, Key):
            self._items.pop(Key.get('id'), None)

    class _DummyResource:
        def Table(self, name):
            return _DummyTable()

    monkeypatch.setattr(boto3, 'resource', lambda *a, **k: _DummyResource())

    import src.dynamodb_service as ds
    class _DummyDynamo:
        def __init__(self, *a, **k):
            # use minimal in-memory behavior; other tests override with richer fake
            self.packages = {}
        def search_packages_by_regex(self, regex):
            return list(self.packages.values())
        def create_package(self, pkg):
            pkg_id = pkg.get('id') or pkg.get('metadata', {}).get('id')
            self.packages[pkg_id] = pkg
            return pkg
        def get_package(self, id):
            return self.packages.get(id)
        def get_all_packages(self):
            return list(self.packages.values())
        def update_package(self, id, data):
            if id in self.packages:
                self.packages[id].update(data)
        def delete_package(self, id):
            if id in self.packages:
                self.packages[id]['is_deleted'] = True
                return True
            return False
        def reset_database(self):
            self.packages.clear()

    ds.DynamoDBService = _DummyDynamo

    import src.storage as st
    class _DummyStorage:
        def __init__(self, *a, **k):
            pass
        def save_package(self, name, url, artifact_type):
            return {"metadata": {"id": f"pkg-{name}", "name": name, "type": artifact_type}, "data": {"url": url}}
        def clear_all_s3_objects(self):
            return True
    st.S3Storage = _DummyStorage

    import src.app as app
    importlib.reload(app)
    return app


class FakeStorage:
    def __init__(self):
        self.saved = []
        self.cleared = False

    def save_package(self, name, url, artifact_type):
        pkg = {
            "metadata": {"id": f"pkg-{name}", "name": name, "type": artifact_type},
            "data": {"url": url}
        }
        self.saved.append(pkg)
        return pkg

    def clear_all_s3_objects(self):
        self.cleared = True


class FakeDynamo:
    def __init__(self):
        self.packages = {}
        self.created = []
        self.updated = []
        self.deleted = []
        self.reset_called = False

    def search_packages_by_regex(self, regex):
        return list(self.packages.values())

    def create_package(self, pkg):
        self.created.append(pkg)
        pkg_id = pkg.get('id') or pkg.get('metadata', {}).get('id')
        self.packages[pkg_id] = pkg
        return pkg

    def get_package(self, id):
        return self.packages.get(id)

    def get_all_packages(self):
        return list(self.packages.values())

    def update_package(self, id, data):
        self.updated.append((id, data))
        if id in self.packages:
            self.packages[id].update(data)

    def delete_package(self, id):
        self.deleted.append(id)
        if id in self.packages:
            self.packages[id]['is_deleted'] = True
            return True
        return False

    def reset_database(self):
        self.packages.clear()
        self.reset_called = True


def test_health_and_tracks_and_authenticate(monkeypatch):
    app = reload_app_with_env(monkeypatch)
    client = app.app.test_client()

    r = client.get('/health')
    assert r.status_code == 200
    d = r.get_json()
    assert d['status'] == 'ok'

    r = client.get('/tracks')
    assert r.status_code == 200
    assert 'plannedTracks' in r.get_json()

    r = client.put('/authenticate')
    assert r.status_code == 501


def test_convert_floats_to_decimals():
    from src.app import convert_floats_to_decimals
    assert isinstance(convert_floats_to_decimals(1.23), Decimal)
    obj = {'a': 1.5, 'b': [2.3, {'c': 3.7}]}
    conv = convert_floats_to_decimals(obj)
    assert conv['a'] == Decimal('1.5')
    assert conv['b'][1]['c'] == Decimal('3.7')


def test_search_by_regex_and_missing(monkeypatch):
    app = reload_app_with_env(monkeypatch)
    fake = FakeDynamo()
    fake.packages['pkg1'] = {'metadata': {'id': 'pkg1', 'name': 'foo', 'type': 'model'}}
    monkeypatch.setattr(app, 'dynamodb_service', fake)
    client = app.app.test_client()

    # Missing body (send empty JSON to avoid UnsupportedMediaType)
    r = client.get('/artifact/byRegex', json={})
    assert r.status_code == 400

    r = client.get('/artifact/byRegex', json={'regex': 'foo'})
    assert r.status_code in (200, 400)

    # Use open with JSON payload to ensure body is parsed
    r = client.open('/artifact/byRegex', method='GET', json={'regex': 'foo'})
    assert r.status_code == 200
    res = r.get_json()
    assert isinstance(res, list)


def test_upload_artifact_model_and_dataset_and_code(monkeypatch):
    app = reload_app_with_env(monkeypatch)
    fake_storage = FakeStorage()
    fake_db = FakeDynamo()
    monkeypatch.setattr(app, 'storage', fake_storage)
    monkeypatch.setattr(app, 'dynamodb_service', fake_db)

    # Stub run_scoring to avoid external calls
    def fake_run_scoring(url):
        return {
            'scores': {'license': {'value': 1.0, 'latency_ms': 1}},
            'model_metadata': {'hf_metadata': {'readme_text': 'readme', 'size_mb': 200}}
        }

    monkeypatch.setattr(app, 'run_scoring', fake_run_scoring)

    client = app.app.test_client()

    # Model
    payload = {'url': 'https://huggingface.co/org/model'}
    r = client.post('/artifact/model', json=payload)
    assert r.status_code == 201
    data = r.get_json()
    assert data['metadata']['type'] == 'model'

    # Dataset
    r = client.post('/artifact/dataset', json={'url': 'https://example.com/ds'})
    assert r.status_code == 201
    d2 = r.get_json()
    assert d2['metadata']['type'] == 'dataset'

    # Code
    r = client.post('/artifact/code', json={'url': 'https://example.com/code'})
    assert r.status_code == 201
    d3 = r.get_json()
    assert d3['metadata']['type'] == 'code'


def test_artifact_endpoints_and_rate_and_cost_and_by_name(monkeypatch):
    app = reload_app_with_env(monkeypatch)
    fake_storage = FakeStorage()
    fake_db = FakeDynamo()
    monkeypatch.setattr(app, 'storage', fake_storage)
    monkeypatch.setattr(app, 'dynamodb_service', fake_db)

    # Create a package and store
    pkg = {'id': 'id1', 'name': 'MyModel', 'artifact_type': 'model', 'metadata': {'id': 'id1', 'name': 'MyModel', 'type': 'model'}, 'data': {'url': 'u'}, 'scores': {
        'net_score': {'value': 0.5, 'latency_ms': 10},
        'size_score': {'value': {'raspberry_pi': 0.5, 'jetson_nano': 0.6, 'desktop_pc': 0.7, 'aws_server': 0.8}, 'latency_ms': 5},
        'license': {'value': 1.0, 'latency_ms': 1}
    }, 'cost': 12.34}
    fake_db.packages['id1'] = pkg

    client = app.app.test_client()

    # Rate
    r = client.get('/artifact/model/id1/rate')
    assert r.status_code == 200
    rate = r.get_json()
    assert rate['name'] == 'MyModel'
    assert isinstance(rate['size_score'], dict)

    # Cost
    r = client.get('/artifact/model/id1/cost')
    assert r.status_code == 200
    cost = r.get_json()
    assert 'id1' in cost

    # By name (case-insensitive)
    r = client.get('/artifact/byName/MyModel')
    assert r.status_code == 200
    arr = r.get_json()
    assert isinstance(arr, list) and arr[0]['id'] == 'id1'


# def test_get_artifact_by_id_put_delete_and_404(monkeypatch):
#     app = reload_app_with_env(monkeypatch)
#     fake_db = FakeDynamo()
#     monkeypatch.setattr(app, 'dynamodb_service', fake_db)
#     client = app.app.test_client()

#     # Non-existent GET
#     r = client.get('/artifacts/model/notfound')
#     assert r.status_code == 404

#     # Put update
#     fake_db.packages['id2'] = {'metadata': {'id': 'id2', 'name': 'n', 'type': 'model'}}
#     r = client.put('/artifacts/model/id2', json={'extra': 1})
#     assert r.status_code == 200
#     assert fake_db.updated

#     # Delete
#     r = client.delete('/artifacts/model/id2')
#     assert r.status_code == 200

#     # Delete non-existent
#     r = client.delete('/artifacts/model/notthere')
#     assert r.status_code == 501


def test_license_lineage_query_and_reset(monkeypatch):
    app = reload_app_with_env(monkeypatch)
    fake_db = FakeDynamo()
    fake_storage = FakeStorage()
    monkeypatch.setattr(app, 'dynamodb_service', fake_db)
    monkeypatch.setattr(app, 'storage', fake_storage)
    client = app.app.test_client()

    # License check - missing package
    r = client.post('/artifact/model/idx/license-check')
    assert r.status_code == 400

    # Add package with license score
    fake_db.packages['id3'] = {'scores': {'license': {'value': 1.0}}}
    r = client.post('/artifact/model/id3/license-check')
    assert r.status_code == 200
    assert r.get_json()['value'] is True

    # Lineage
    r = client.get('/artifact/model/id3/lineage')
    assert r.status_code == 200

    # Query artifacts
    fake_db.packages['id4'] = {'metadata': {'id': 'id4', 'name': 'alpha', 'type': 'model'}}
    r = client.post('/artifacts', json=[{"name": "alpha", "types": ["model"]}])
    assert r.status_code == 200

    # Reset
    r = client.delete('/reset')
    assert r.status_code == 200
    assert fake_storage.cleared
    assert fake_db.reset_called


def test_run_scoring_and_error_handlers(monkeypatch):
    app = reload_app_with_env(monkeypatch)
    # stub HFModelURL and HFModel to avoid external parsing
    class FakeModelURL:
        def __init__(self, url):
            self.url = url
            self.code = ['https://github.com/org/repo']
            self.datasets = []

    class FakeModel:
        def __init__(self, model_url):
            self.model_url = model_url
            self.metadata = {}

    monkeypatch.setattr(app, 'HFModelURL', FakeModelURL)
    monkeypatch.setattr(app, 'HFModel', FakeModel)
    monkeypatch.setattr(app, 'fetch_repo_metadata', lambda m: {'readme_text': 'readme', 'size_mb': 100})
    monkeypatch.setenv('GITHUB_TOKEN', 'gh123')
    monkeypatch.setattr(app, 'fetch_bus_factor_raw_contributors', lambda url, token: {'contributors': []})

    class R:
        def __init__(self, name, value, latency_ms=1):
            self.name = name
            self.value = value
            self.latency_ms = latency_ms

    monkeypatch.setattr(app, 'compute_all_metrics', lambda meta, metrics, max_workers=8: [R('license', 1.0, 1), R('ramp_up_time', 0.5, 2)])

    res = app.run_scoring('https://huggingface.co/org/model')
    assert 'scores' in res and 'net_score' in res['scores']

    # Test error handlers directly using request contexts
    from werkzeug.exceptions import Unauthorized, Forbidden

    with app.app.test_request_context('/', headers={'Accept': 'text/html'}):
        html_resp, code = app.unauthorized(Unauthorized('no'))
        assert code == 401

    with app.app.test_request_context('/', headers={'Accept': 'application/json'}):
        json_resp, code = app.forbidden(Forbidden('denied'))
        assert code == 403


def test_load_secrets_from_aws(monkeypatch):
    # Clear env vars and stub Secrets Manager
    keys = ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_DEFAULT_REGION", "FLASK_SECRET_KEY", "GITHUB_TOKEN", "HF_TOKEN", "S3_BUCKET_NAME"]
    for k in keys:
        monkeypatch.delenv(k, raising=False)

    class DummySM:
        def get_secret_value(self, SecretId):
            return {"SecretString": json.dumps({
                "AWS_ACCESS_KEY_ID": "A1",
                "AWS_SECRET_ACCESS_KEY": "S1",
                "FLASK_SECRET_KEY": "F1",
                "GITHUB_TOKEN": "G1",
                "HF_TOKEN": "H1",
                "S3_BUCKET_NAME": "B1"
            })}

    import importlib
    import src.storage as st
    import src.dynamodb_service as ds

    # ensure original classes are used but replace with no-op implementations to avoid AWS/network
    importlib.reload(st)
    st.S3Storage = lambda *a, **k: None
    importlib.reload(ds)
    ds.DynamoDBService = lambda *a, **k: None

    import boto3
    monkeypatch.setattr(boto3, 'client', lambda *a, **k: DummySM())

    # prevent DynamoDB from doing network calls by stubbing boto3.resource
    class DummyTable:
        def __init__(self):
            self.table_name = 'dummy'
            self.table_status = 'ACTIVE'
        def put_item(self, Item):
            return None
        def get_item(self, Key):
            return {}
        def scan(self, **k):
            return {'Items': []}
    class DummyResource:
        def Table(self, name):
            return DummyTable()
    monkeypatch.setattr(boto3, 'resource', lambda *a, **k: DummyResource())

    import src.app as app_mod
    importlib.reload(app_mod)
    assert app_mod.FLASK_SECRET_KEY == 'F1'


def test_artifact_type_and_put_no_data_and_method_not_allowed(monkeypatch):
    app = reload_app_with_env(monkeypatch)
    fake_db = FakeDynamo()
    monkeypatch.setattr(app, 'dynamodb_service', fake_db)
    client = app.app.test_client()

    # Invalid artifact type
    r = client.post('/artifact/invalidtype', json={'url': 'x'})
    assert r.status_code == 400

    # PUT with no data should return 400
    fake_db.packages['id5'] = {'metadata': {'id': 'id5', 'name': 'n', 'type': 'model'}}
    # send explicit empty JSON (null) with application/json content type
    r = client.open('/artifacts/model/id5', method='PUT', data='null', content_type='application/json')
    assert r.status_code == 400

    # Method not allowed (POST on a GET/PUT/DELETE route)
    r = client.post('/artifacts/model/id5', json={})
    assert r.status_code == 405


def test_query_artifacts_wildcard(monkeypatch):
    app = reload_app_with_env(monkeypatch)
    fake_db = FakeDynamo()
    fake_db.packages['wild1'] = {'metadata': {'id': 'wild1', 'name': 'alpha', 'type': 'model'}}
    monkeypatch.setattr(app, 'dynamodb_service', fake_db)
    client = app.app.test_client()

    r = client.post('/artifacts', json=[{"name": "*", "types": []}])
    assert r.status_code == 200
    res = r.get_json()
    assert any(p['id'] == 'wild1' for p in res)


def test_run_scoring_size_score_and_exception(monkeypatch):
    app = reload_app_with_env(monkeypatch)

    class FakeModelURL:
        def __init__(self, url):
            self.url = url
            self.code = []
            self.datasets = []

    class FakeModel:
        def __init__(self, model_url):
            self.model_url = model_url
            self.metadata = {}

    monkeypatch.setattr(app, 'HFModelURL', FakeModelURL)
    monkeypatch.setattr(app, 'HFModel', FakeModel)
    monkeypatch.setattr(app, 'fetch_repo_metadata', lambda m: {'readme_text': 'r', 'size_mb': 1})

    class R:
        def __init__(self, name, value, latency_ms=1):
            self.name = name
            self.value = value
            self.latency_ms = latency_ms

    # size_score as dict should be averaged correctly
    monkeypatch.setattr(app, 'compute_all_metrics', lambda meta, metrics, max_workers=8: [R('size_score', {'raspberry_pi': 1.0, 'jetson_nano': 0.5, 'desktop_pc': 0.5, 'aws_server': 0.5}, 1), R('license', 1.0, 1)])
    res = app.run_scoring('https://huggingface.co/org/model')
    assert 'scores' in res
    assert 'net_score' in res['scores']

    # simulate compute_all_metrics raising an exception
    def boom(meta, metrics, max_workers=8):
        raise RuntimeError('boom')

    monkeypatch.setattr(app, 'compute_all_metrics', boom)
    res2 = app.run_scoring('https://huggingface.co/org/model')
    assert 'net_score' in res2 and res2['net_score']['value'] == 0.0
    assert isinstance(res2['error'], Exception)


def test_upload_artifact_db_failure_returns_500(monkeypatch):
    app = reload_app_with_env(monkeypatch)
    # storage returns package info but DB create returns None
    class BadDB(FakeDynamo):
        def create_package(self, pkg):
            return None

    fake_storage = FakeStorage()
    bad_db = BadDB()
    monkeypatch.setattr(app, 'storage', fake_storage)
    monkeypatch.setattr(app, 'dynamodb_service', bad_db)

    # stub run_scoring
    monkeypatch.setattr(app, 'run_scoring', lambda url: {'scores': {}, 'model_metadata': {}})

    client = app.app.test_client()
    r = client.post('/artifact/model', json={'url': 'https://huggingface.co/org/model'})
    assert r.status_code == 500


def test_search_by_regex_value_error(monkeypatch):
    app = reload_app_with_env(monkeypatch)
    class ErrDB(FakeDynamo):
        def search_packages_by_regex(self, regex):
            raise ValueError('bad regex')

    monkeypatch.setattr(app, 'dynamodb_service', ErrDB())
    client = app.app.test_client()
    r = client.get('/artifact/byRegex', json={'regex': 'x'})
    assert r.status_code == 400


def test_upload_artifact_db_exception(monkeypatch):
    app = reload_app_with_env(monkeypatch)
    fake_storage = FakeStorage()
    class ExplodingDB(FakeDynamo):
        def create_package(self, pkg):
            raise RuntimeError('boom')

    monkeypatch.setattr(app, 'storage', fake_storage)
    monkeypatch.setattr(app, 'dynamodb_service', ExplodingDB())
    monkeypatch.setattr(app, 'run_scoring', lambda url: {'scores': {}, 'model_metadata': {}})
    client = app.app.test_client()
    r = client.post('/artifact/model', json={'url': 'https://huggingface.co/org/model'})
    assert r.status_code == 500
    j = r.get_json()
    assert 'error' in j and 'id' in j


def test_get_artifact_cost_and_by_name_not_found_and_invalid_type(monkeypatch):
    app = reload_app_with_env(monkeypatch)
    fake_db = FakeDynamo()
    monkeypatch.setattr(app, 'dynamodb_service', fake_db)
    client = app.app.test_client()

    # cost not found
    r = client.get('/artifact/model/notthere/cost')
    assert r.status_code == 404

    # byName not found
    r = client.get('/artifact/byName/nothing')
    assert r.status_code == 404

    # invalid type for get_artifact_by_id
    r = client.get('/artifacts/invalidtype/x')
    assert r.status_code == 400


# def test_query_artifacts_skip_deleted(monkeypatch):
#     app = reload_app_with_env(monkeypatch)
#     fake_db = FakeDynamo()
#     fake_db.packages['a'] = {'metadata': {'id': 'a', 'name': 'keep', 'type': 'model'}, 'is_deleted': False}
#     fake_db.packages['b'] = {'metadata': {'id': 'b', 'name': 'gone', 'type': 'model'}, 'is_deleted': True}
#     monkeypatch.setattr(app, 'dynamodb_service', fake_db)
#     client = app.app.test_client()

#     r = client.post('/artifacts', json=[{"name": "*", "types": []}])
#     assert r.status_code == 200
#     res = r.get_json()
#     assert any(p['id'] == 'a' for p in res) and all(p['id'] != 'b' for p in res)


def test_reset_system_handles_exceptions(monkeypatch):
    app = reload_app_with_env(monkeypatch)
    class BadStorage(FakeStorage):
        def clear_all_s3_objects(self):
            raise RuntimeError('s3 fail')

    class BadDB(FakeDynamo):
        def reset_database(self):
            raise RuntimeError('db fail')

    monkeypatch.setattr(app, 'storage', BadStorage())
    monkeypatch.setattr(app, 'dynamodb_service', BadDB())
    client = app.app.test_client()
    r = client.delete('/reset')
    assert r.status_code == 200


def test_run_scoring_handles_repo_fetch_exception(monkeypatch):
    app = reload_app_with_env(monkeypatch)

    class FakeModelURL:
        def __init__(self, url):
            self.url = url
            self.code = ['https://github.com/org/repo']
            self.datasets = []

    class FakeModel:
        def __init__(self, model_url):
            self.model_url = model_url
            self.metadata = {}

    monkeypatch.setattr(app, 'HFModelURL', FakeModelURL)
    monkeypatch.setattr(app, 'HFModel', FakeModel)
    monkeypatch.setattr(app, 'fetch_repo_metadata', lambda m: {'readme_text': 'r', 'size_mb': 1})
    monkeypatch.setenv('GITHUB_TOKEN', 'gh123')
    monkeypatch.setattr(app, 'fetch_bus_factor_raw_contributors', lambda url, token: (_ for _ in ()).throw(RuntimeError('fail')))

    class R:
        def __init__(self, name, value, latency_ms=1):
            self.name = name
            self.value = value
            self.latency_ms = latency_ms

    monkeypatch.setattr(app, 'compute_all_metrics', lambda meta, metrics, max_workers=8: [R('license', 1.0, 1)])
    res = app.run_scoring('https://huggingface.co/org/model')
    assert 'scores' in res and 'net_score' in res['scores']
