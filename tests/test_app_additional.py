import importlib
import json
import src.app as app


def test_search_by_regex_missing_regex(monkeypatch):
    importlib.reload(app)
    client = app.app.test_client()
    rv = client.get('/artifact/byRegex', json={})
    assert rv.status_code == 400
    assert b'regex field is required' in rv.data


def test_search_by_regex_value_error(monkeypatch):
    importlib.reload(app)
    client = app.app.test_client()
    # make dynamodb raise ValueError to hit the except
    monkeypatch.setattr(app, 'dynamodb_service', type('D', (), {'search_packages_by_regex': staticmethod(lambda r: (_ for _ in ()).throw(ValueError('bad')))}))
    rv = client.get('/artifact/byRegex', json={'regex': '['})
    assert rv.status_code == 400


def test_upload_artifact_invalid_type():
    importlib.reload(app)
    client = app.app.test_client()
    rv = client.post('/artifact/invalidtype', json={'url': 'https://x'})
    assert rv.status_code == 400


def test_upload_artifact_dataset_and_save(monkeypatch):
    importlib.reload(app)
    client = app.app.test_client()

    # stub storage.save_package to return a package structure
    pkg = {
        'metadata': {'id': '123', 'name': 'org-dataset', 'type': 'dataset'},
        'data': {'url': 'https://huggingface.co/org/dataset'}
    }
    monkeypatch.setattr(app, 'storage', type('S', (), {'save_package': staticmethod(lambda **k: pkg)}))
    monkeypatch.setattr(app, 'dynamodb_service', type('D', (), {'create_package': staticmethod(lambda p: p)}))

    rv = client.post('/artifact/dataset', json={'url': 'https://huggingface.co/org/dataset'})
    assert rv.status_code == 201
    body = json.loads(rv.data)
    assert body['metadata']['id'] == '123'


def test_get_artifact_put_no_data(monkeypatch):
    importlib.reload(app)
    client = app.app.test_client()
    # PUT with explicit null JSON body to avoid 415
    rv = client.put('/artifacts/model/1', data='null', content_type='application/json')
    assert rv.status_code == 400


def test_license_check_true_and_false(monkeypatch):
    importlib.reload(app)
    client = app.app.test_client()

    # license acceptable
    monkeypatch.setattr(app, 'dynamodb_service', type('D', (), {'get_package': staticmethod(lambda _id: {'scores': {'license': {'value': 1.0}}})}))
    rv = client.post('/artifact/model/1/license-check', json={'github_url': 'https://github.com/x'})
    assert rv.status_code == 200
    assert json.loads(rv.data)['value'] is True

    # license not acceptable -> missing package
    monkeypatch.setattr(app, 'dynamodb_service', type('D', (), {'get_package': staticmethod(lambda _id: None)}))
    rv2 = client.post('/artifact/model/2/license-check', json={'github_url': 'https://github.com/x'})
    assert rv2.status_code == 400


def test_reset_system_with_errors(monkeypatch):
    importlib.reload(app)
    client = app.app.test_client()

    # make storage.clear_all_s3_objects raise
    monkeypatch.setattr(app, 'storage', type('S', (), {'clear_all_s3_objects': staticmethod(lambda : (_ for _ in ()).throw(Exception('boom')))}))
    # make dynamodb reset raise
    monkeypatch.setattr(app, 'dynamodb_service', type('D', (), {'reset_database': staticmethod(lambda : (_ for _ in ()).throw(Exception('ugh')))}))

    rv = client.delete('/reset')
    assert rv.status_code == 200
    body = json.loads(rv.data)
    assert body['success'] is True


def test_get_artifact_id_invalid_and_delete_paths(monkeypatch):
    importlib.reload(app)
    client = app.app.test_client()

    # invalid artifact type on GET
    rv = client.get('/artifacts/invalid/1')
    assert rv.status_code == 400

    # package missing -> 404
    monkeypatch.setattr(app, 'dynamodb_service', type('D', (), {'get_package': staticmethod(lambda _id: None)}))
    rv2 = client.get('/artifacts/model/1')
    assert rv2.status_code == 404

    # DELETE not implemented
    monkeypatch.setattr(app, 'dynamodb_service', type('D', (), {'delete_package': staticmethod(lambda _id: False)}))
    rv3 = client.delete('/artifacts/model/1')
    assert rv3.status_code == 501

    # DELETE success
    monkeypatch.setattr(app, 'dynamodb_service', type('D', (), {'delete_package': staticmethod(lambda _id: True)}))
    rv4 = client.delete('/artifacts/model/1')
    assert rv4.status_code == 200


def test_get_artifact_by_name_not_found(monkeypatch):
    importlib.reload(app)
    client = app.app.test_client()
    monkeypatch.setattr(app, 'dynamodb_service', type('D', (), {'get_all_packages': staticmethod(lambda : [])}))
    rv = client.get('/artifact/byName/somename')
    assert rv.status_code == 404


def test_secrets_manager_loading(monkeypatch):
    # Remove env vars so app will attempt to load from Secrets Manager
    keys = ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_DEFAULT_REGION", "FLASK_SECRET_KEY", "GITHUB_TOKEN", "HF_TOKEN", "S3_BUCKET_NAME"]
    for k in keys:
        monkeypatch.delenv(k, raising=False)

    # Fake boto3 secrets client
    import json as _json
    class FakeSecretsClient:
        def get_secret_value(self, SecretId=None):
            return {"SecretString": _json.dumps({
                "AWS_ACCESS_KEY_ID": "ak",
                "AWS_SECRET_ACCESS_KEY": "sk",
                "FLASK_SECRET_KEY": "fk",
                "GITHUB_TOKEN": "gt",
                "HF_TOKEN": "ht",
                "S3_BUCKET_NAME": "bucket"
            })}

    import boto3 as _boto3
    monkeypatch.setattr(_boto3, 'client', lambda *a, **k: FakeSecretsClient())

    # Stub S3Storage and DynamoDBService to avoid network calls during import
    import sys
    import types
    fake_storage = types.ModuleType('storage')
    fake_storage.S3Storage = lambda *a, **k: object()
    sys.modules['storage'] = fake_storage

    fake_ddb = types.ModuleType('dynamodb_service')
    fake_ddb.DynamoDBService = lambda *a, **k: object()
    sys.modules['dynamodb_service'] = fake_ddb

    # Reload app module to trigger secrets-loading branch
    import importlib as _importlib
    _importlib.reload(app)

    assert app.AWS_ACCESS_KEY == 'ak'
    assert app.GITHUB_TOKEN == 'gt'
