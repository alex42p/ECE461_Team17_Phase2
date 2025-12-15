import importlib
import boto3
from decimal import Decimal

import pytest


def make_dummy_boto(monkeypatch):
    class DummyTable:
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
            values = kwargs.get('ExpressionAttributeValues', {})
            # write back values for easy inspection
            if key in self._items:
                # map values like ':k': val into storage under 'updated'
                for k, v in values.items():
                    self._items[key][k] = v
                return {'Attributes': self._items[key]}
            return {'Attributes': {}}
        def delete_item(self, Key):
            self._items.pop(Key.get('id'), None)
        def query(self, **kwargs):
            return {'Items': list(self._items.values())}
        def batch_writer(self):
            class BW:
                def __init__(self, items):
                    self._items = items
                def __enter__(self):
                    return self
                def __exit__(self, exc_type, exc, tb):
                    return False
                def delete_item(self, Key):
                    self._items.pop(Key.get('id'), None)
            return BW(self._items)

    class DummyResource:
        def Table(self, name):
            return DummyTable()

    monkeypatch.setattr(boto3, 'resource', lambda *a, **k: DummyResource())


def test_dynamodb_init_missing_credentials():
    import importlib
    import src.dynamodb_service as ds
    importlib.reload(ds)
    from src.dynamodb_service import DynamoDBService
    with pytest.raises(ValueError):
        DynamoDBService(None, None, None)


def test_dynamodb_crud_and_conversions(monkeypatch):
    import importlib
    import src.dynamodb_service as ds
    importlib.reload(ds)
    make_dummy_boto(monkeypatch)
    from src.dynamodb_service import DynamoDBService

    svc = DynamoDBService('A', 'B', 'us-east-1')

    pkg = {'id': 'p1', 'metadata': {'id': 'p1'}, 'cost': 12.5}
    created = svc.create_package(pkg)
    assert created.get('metadata', {}).get('id') == 'p1'

    fetched = svc.get_package('p1')
    assert fetched is not None
    assert isinstance(fetched.get('cost'), float)

    all_pkgs = svc.get_all_packages()
    assert isinstance(all_pkgs, list)

    # update package
    svc.packages_table.put_item(Item={'id': 'p2', 'metadata': {'id': 'p2'}})
    updated = svc.update_package('p2', {'new_field': 3.14})
    assert updated is not None

    # delete (soft)
    svc.packages_table.put_item(Item={'id': 'p3', 'metadata': {'id': 'p3'}})
    svc.delete_package('p3')

    # query and search
    svc.packages_table.put_item(Item={'id': 'n1', 'name': 'alpha', 'is_deleted': False})
    assert svc.query_packages_by_name('alpha')
    assert svc.query_packages_by_type('model') == [] or isinstance(svc.query_packages_by_type('model'), list)
    assert svc.search_packages_by_regex('alpha')

    # reset database (uses batch_writer)
    svc.packages_table.put_item(Item={'id': 'to_delete', 'name': 'todel'})
    svc.reset_database()


def test_convert_helpers(monkeypatch):
    import importlib
    import src.dynamodb_service as ds
    importlib.reload(ds)
    make_dummy_boto(monkeypatch)
    from src.dynamodb_service import DynamoDBService
    svc = DynamoDBService('A', 'B', 'us-east-1')

    obj = {'a': 1.23, 'b': [2.5, {'c': 3.75}]}
    conv = svc._convert_floats_to_decimal(obj)
    # nested floats become Decimal
    assert isinstance(conv['a'], Decimal)

    back = svc._convert_decimals_to_float(conv)
    assert isinstance(back['a'], float)
