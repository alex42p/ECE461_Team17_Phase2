import json
import src.app as app_module


def test_artifacts_echo_offset_header(monkeypatch):
    # Arrange: stub DynamoDB to return one package
    monkeypatch.setattr(app_module.dynamodb_service, "get_all_packages", lambda: [
        {"metadata": {"id": "1", "name": "audience-classifier", "type": "model"}, "is_deleted": False}
    ])

    client = app_module.app.test_client()

    # Act: call endpoint with offset query param
    resp = client.post('/artifacts?offset=abc123', data=json.dumps([{"name": "*"}]), content_type='application/json')

    # Assert
    assert resp.status_code == 200
    assert resp.get_json() == [{"id": "1", "name": "audience-classifier", "type": "model"}]
    assert resp.headers.get('offset') == 'abc123'
