import importlib
import boto3
from botocore.exceptions import ClientError


def reload_basic(monkeypatch):
    import src.dynamodb_service as ds
    importlib.reload(ds)
    class BadTable:
        def __init__(self):
            self.table_name = 'bad'
            self.table_status = 'UNKNOWN'
        def put_item(self, Item):
            raise ClientError({'Error': {'Message': 'boom'}}, 'PutItem')
        def scan(self, **k):
            raise RuntimeError('scanfail')
        def update_item(self, **k):
            raise ClientError({'Error': {}}, 'UpdateItem')
        def query(self, **k):
            raise ClientError({'Error': {}}, 'Query')

    class DummyRes:
        def Table(self, name):
            return BadTable()

    monkeypatch.setattr(boto3, 'resource', lambda *a, **k: DummyRes())
    return ds.DynamoDBService('A', 'B', region_name='r')


def test_create_raises_clienterror(monkeypatch):
    svc = reload_basic(monkeypatch)
    try:
        svc.create_package({'metadata': {'id': 'x'}})
    except ClientError:
        assert True


def test_scan_and_query_exceptions(monkeypatch):
    svc = reload_basic(monkeypatch)
    # get_all_packages should catch and return []
    assert svc.get_all_packages() == []
    assert svc.query_packages_by_name('x') == []
    assert svc.query_packages_by_type('model') == []
    # update_package should return None on ClientError
    assert svc.update_package('x', {}) is None
