from types import SimpleNamespace
import datetime
import pytest
from unittest.mock import MagicMock

import src.audit_service as audit_service

class FakeAuditLog:
    def __init__(self, artifact_id, artifact_type, action, username, timestamp, details):
        self.id = 1
        self.artifact_id = artifact_id
        self.artifact_type = artifact_type
        self.action = action
        self.username = username
        self.timestamp = timestamp
        self.details = details

    def to_dict(self):
        return {
            'id': self.id,
            'artifact_id': self.artifact_id,
            'artifact_type': self.artifact_type,
            'action': getattr(self.action, 'value', str(self.action)),
            'username': self.username,
            'timestamp': self.timestamp.isoformat(),
            'details': self.details
        }

class FakeLog:
    def __init__(self, artifact_id):
        self.artifact_id = artifact_id
        self.username = 'u'
        self.action = SimpleNamespace(value='CREATE')
        self.timestamp = __import__('datetime').datetime.utcnow()
        self.details = {}

    def to_dict(self):
        return {'artifact_id': self.artifact_id, 'username': self.username, 'action': self.action.value, 'timestamp': self.timestamp.isoformat(), 'details': self.details}


class FakeQuery:
    def __init__(self, items):
        self._items = items

    def filter(self, *a, **k):
        return self

    def filter_by(self, **k):
        return self

    def order_by(self, *a, **k):
        return self

    def limit(self, n):
        return self

    def offset(self, n):
        return self

    def all(self):
        return self._items

    def count(self):
        return len(self._items)

class FakeSession:
    def __init__(self, logs = None):
        self.logs = logs

    def query(self, model):
        return FakeQuery(self.logs)

    def add(self, obj):
        pass

    def flush(self):
        pass

def test_log_action_and_wrappers(monkeypatch):
    # Replace AuditLog class with a fake one that records inputs
    monkeypatch.setattr(audit_service, 'AuditLog', FakeAuditLog)

    session = FakeSession()
    svc = audit_service.AuditService(session)

    entry = svc.log_action('pkg1', 'model', 'CREATE', username='alice', details={'k': 'v'})
    assert entry.artifact_id == 'pkg1'
    assert entry.username == 'alice'

    c = svc.log_create('pkg1', 'model', username='bob', artifact_name='n', artifact_version='v')
    assert 'name' in c.details

    d = svc.log_download('pkg2', 'model', username='u', download_size=123)
    assert d.details['download_size_bytes'] == 123


def test_get_audit_statistics_monkeypatched(monkeypatch):
    # Monkeypatch session.query to return predictable aggregates
    class FakeSession:
        def query(self, *a, **k):
            class Q:
                def group_by(self, *a, **k):
                    return self

                def all(self):
                    # return list of tuples (action, count)
                    return [(MagicMock(value='CREATE'), 2), (MagicMock(value='DOWNLOAD'), 1)]

                def scalar(self):
                    return 5

            return Q()

    monkeypatch.setattr(audit_service, 'AuditLog', MagicMock())
    session = FakeSession()
    svc = audit_service.AuditService(session)
    stats = svc.get_audit_statistics()
    assert 'total_events' in stats
    assert 'action_breakdown' in stats



def test_get_trails_and_stats():
    logs = [FakeLog('p1'), FakeLog('p2')]
    session = FakeSession(logs)
    svc = audit_service.AuditService(session)

    trail = svc.get_artifact_audit_trail('p1')
    assert isinstance(trail, list)

    user_trail = svc.get_user_audit_trail('u')
    assert isinstance(user_trail, list)

    downloads = svc.get_download_history('p1')
    assert isinstance(downloads, list)

    count = svc.get_action_count('p1')
    assert isinstance(count, int)

    recent = svc.get_recent_activity()
    assert isinstance(recent, list)
