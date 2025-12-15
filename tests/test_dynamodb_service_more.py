import importlib
import boto3
from decimal import Decimal


def make_dummy_table():
    class DummyTable:
        def __init__(self):
            self.table_name = 'dummy'
            self.table_status = 'ACTIVE'
            self._items = {}

        def put_item(self, Item):
            # Accept both top-level 'id' and nested metadata
            if 'metadata' in Item and Item['metadata'].get('id'):
                key = Item['metadata']['id']
            else:
                key = Item.get('id') or Item.get('metadata', {}).get('id')
            self._items[key] = Item

        def get_item(self, Key):
            item = self._items.get(Key.get('id'))
            # Simulate that deleted items are not returned by DynamoDB get
            if item and item.get('is_deleted', False):
                return {}
            return {'Item': item} if item else {}

        def scan(self, **kwargs):
            return {'Items': list(self._items.values())}

        def update_item(self, **kwargs):
            key = kwargs['Key']['id']
            attrs = kwargs.get('ExpressionAttributeValues', {})
            # emulate DynamoDB returning Attributes with Decimal fields
            # handle special case for soft delete keys
            if ':true' in attrs:
                self._items.setdefault(key, {})['is_deleted'] = True
            if ':timestamp' in attrs:
                self._items.setdefault(key, {})['timestamp'] = attrs[':timestamp']
            attrs_converted = {k.strip(':'): (Decimal(str(v)) if isinstance(v, float) else v) for k, v in attrs.items() if k not in (':true', ':timestamp')}
            self._items.setdefault(key, {}).update(attrs_converted)
            return {'Attributes': self._items.get(key)}

        def delete_item(self, Key):
            self._items.pop(Key.get('id'), None)

        def query(self, **kwargs):
            return {'Items': list(self._items.values())}

        def batch_writer(self):
            class BW:
                def __init__(self, items):
                    self.items = items
                def __enter__(self):
                    return self
                def delete_item(self, Key):
                    self.items.pop(Key.get('id'), None)
                def __exit__(self, exc_type, exc, tb):
                    return False
            return BW(self._items)

    return DummyTable()


def reload_service(monkeypatch):
    import src.dynamodb_service as ds
    importlib.reload(ds)
    class DummyRes:
        def Table(self, name):
            return make_dummy_table()

    monkeypatch.setattr(boto3, 'resource', lambda *a, **k: DummyRes())
    return ds.DynamoDBService('A', 'B', region_name='r')


def test_create_get_update_delete_and_query(monkeypatch):
    svc = reload_service(monkeypatch)

    pkg = {'metadata': {'id': 'p1', 'name': 'foo', 'type': 'model'}, 'cost': 12.34}
    created = svc.create_package(pkg)
    assert created is not None

    fetched = svc.get_package('p1')
    assert fetched is not None and fetched['metadata']['id'] == 'p1'

    # update
    updated = svc.update_package('p1', {'extra': 1.0})
    assert isinstance(updated, dict)

    # delete soft
    assert svc.delete_package('p1', soft_delete=True) is True

    # ensure deleted items return None
    assert svc.get_package('p1') is None

    # recreate and hard delete
    svc.create_package(pkg)
    assert svc.delete_package('p1', soft_delete=False) is True

    # query by name and type
    svc.create_package({'metadata': {'id': 'p2', 'name': 'alpha', 'type': 'model'}})
    res_name = svc.query_packages_by_name('alpha')
    assert isinstance(res_name, list) and any(r['metadata']['name'] == 'alpha' for r in res_name)


def test_convert_helpers_and_search_regex(monkeypatch):
    svc = reload_service(monkeypatch)
    # float -> Decimal
    d = svc._convert_floats_to_decimal({'a': 1.23, 'b': [2.3]})
    assert isinstance(d['a'], Decimal)

    # Decimal -> float
    f = svc._convert_decimals_to_float({'a': Decimal('1.5'), 'b': [Decimal('2.0')]})
    assert isinstance(f['a'], float)

    # search invalid regex
    assert svc.search_packages_by_regex('[') == []

    # search matches name and readme
    svc.packages_table.put_item(Item={'id': 'x', 'name': 'findme', 'readme': '', 'is_deleted': False})
    res = svc.search_packages_by_regex('find')
    assert any('findme' in str(item) for item in res)


def test_clear_table_and_reset(monkeypatch):
    svc = reload_service(monkeypatch)
    # populate items
    svc.packages_table.put_item(Item={'id': 'a'})
    svc.packages_table.put_item(Item={'id': 'b'})

    # clear table should not raise
    svc._clear_table(svc.packages_table, 'id')

    # reset_database should call _clear_table
    svc.reset_database()
