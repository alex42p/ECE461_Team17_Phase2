import importlib
from decimal import Decimal
import src.dynamodb_service as ds


class FakeTable:
    def __init__(self):
        self.items = {}

    @property
    def table_name(self):
        return 'fake-table'

    @property
    def table_status(self):
        return 'ACTIVE'

    def put_item(self, Item):
        self.items[Item['metadata']['id']] = Item

    def get_item(self, Key):
        item = self.items.get(Key['id'])
        return {'Item': item} if item is not None else {}

    def scan(self, **kwargs):
        return {'Items': list(self.items.values())}

    def update_item(self, Key=None, **kwargs):
        # emulate returning new attributes
        attrs = self.items.get(Key['id'], {}).copy()
        attrs.update(kwargs.get('ExpressionAttributeValues', {}))
        # convert Decimal objects to Decimal if present
        self.items[Key['id']] = attrs
        return {'Attributes': attrs}

    def delete_item(self, Key=None):
        self.items.pop(Key['id'], None)

    def query(self, **kwargs):
        # naive implementation: filter by 'name' or 'artifact_type'
        name = kwargs.get('ExpressionAttributeValues', {}).get(':name')
        typ = kwargs.get('ExpressionAttributeValues', {}).get(':type')
        items = list(self.items.values())
        if name:
            res = [i for i in items if i.get('name') == name and not i.get('is_deleted', False)]
        elif typ:
            res = [i for i in items if i.get('artifact_type') == typ and not i.get('is_deleted', False)]
        else:
            res = []
        return {'Items': res}

    class Batch:
        def __init__(self, table):
            self.table = table

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def delete_item(self, Key=None):
            self.table.delete_item(Key=Key)

    def batch_writer(self):
        return FakeTable.Batch(self)


class FakeResource:
    def __init__(self, table):
        self._table = table

    def Table(self, name):
        return self._table


def test_dynamodb_basic_crud_and_search(monkeypatch):
    fake = FakeTable()
    monkeypatch.setattr(ds.boto3, 'resource', lambda *a, **k: FakeResource(fake))
    # instantiate service
    service = ds.DynamoDBService('a', 'b', 'us-east-1')

    pkg = {'metadata': {'id': 'p1', 'name': 'MyName', 'type': 'model'}, 'name': 'MyName', 'artifact_type': 'model', 'cost': 1.23}
    created = service.create_package(pkg)
    assert created['metadata']['id'] == 'p1'

    got = service.get_package('p1')
    assert isinstance(got['cost'], float)

    # update package
    updated = service.update_package('p1', {'metadata': {'id': 'p1'}, 'scores': {'net_score': 0.9}})
    assert updated is not None

    # delete package (soft delete)
    res = service.delete_package('p1', soft_delete=True)
    assert res is True

    # query by name/type
    fake.items['p2'] = {'id': 'p2', 'name': 'Other', 'artifact_type': 'dataset'}
    by_name = service.query_packages_by_name('Other')
    assert isinstance(by_name, list)
    by_type = service.query_packages_by_type('dataset')
    assert isinstance(by_type, list)

    # invalid regex returns empty list
    assert service.search_packages_by_regex('[') == []


def test_clear_table_pagination(monkeypatch):
    # create a fake table that pages
    class PagedTable:
        def __init__(self):
            self.calls = 0
            self.deleted = []
        def scan(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return {'Items': [{'id': 'p1'}], 'LastEvaluatedKey': {'id': 'p1'}}
            else:
                return {'Items': []}
        def batch_writer(self):
            class B:
                def __init__(self, parent):
                    self.parent = parent
                def __enter__(self):
                    return self
                def __exit__(self, exc_type, exc, tb):
                    return False
                def delete_item(self, Key=None):
                    self.parent.deleted.append(Key)
            return B(self)

    table = PagedTable()
    service = ds.DynamoDBService.__new__(ds.DynamoDBService)
    # directly call _clear_table with our paged table
    service._clear_table(table, 'id')
    assert table.deleted != []
