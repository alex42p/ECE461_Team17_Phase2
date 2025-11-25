import pytest
from types import SimpleNamespace
import src.health_monitor as hm


def test_record_request_and_route_stats():
    monitor = hm.HealthMonitor()
    monitor.record_request('/a', True)
    monitor.record_request('/a', False)
    monitor.record_request('/b', True)

    stats = monitor.get_route_statistics()
    assert stats['total_requests'] == 3
    assert stats['routes']['/a']['count'] == 2
    assert stats['routes']['/a']['errors'] == 1


def test_format_uptime_and_get_health_summary(monkeypatch):
    monitor = hm.HealthMonitor()
    s = monitor._format_uptime()
    assert isinstance(s, str)

    # Mock component checks to return known states
    monkeypatch.setattr(monitor, 'get_component_health', lambda: [
        SimpleNamespace(name='db', status='ok', response_time_ms=1, error_message=None, last_checked=None, details=None),
        SimpleNamespace(name='s3', status='degraded', response_time_ms=2, error_message=None, last_checked=None, details=None),
        SimpleNamespace(name='gh', status='ok', response_time_ms=3, error_message=None, last_checked=None, details=None),
        SimpleNamespace(name='hf', status='ok', response_time_ms=4, error_message=None, last_checked=None, details=None),
    ])

    summary = monitor.get_health_summary()
    assert summary['status'] == 'degraded'
    assert 'components' in summary


def test_check_database_and_apis_failures(monkeypatch):
    monitor = hm.HealthMonitor()

    # Simulate get_db raising exception for DB check by patching database.get_db
    import src.database as sdb
    monkeypatch.setattr(sdb, 'get_db', lambda: (_ for _ in ()).throw(Exception('dbfail')))
    db_health = monitor.check_database_health()
    assert db_health.status == 'critical'

    # Simulate boto3 client missing -> S3 unknown
    # Force check_s3_health to raise by monkeypatching boto3.client
    monkeypatch.setattr('boto3.client', lambda *a, **k: (_ for _ in ()).throw(Exception('no s3')))
    s3 = monitor.check_s3_health()
    assert s3.status in ('unknown', 'critical')
