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


# def test_check_database_and_apis_failures(monkeypatch):
#     monitor = hm.HealthMonitor()

#     # Simulate get_db raising exception for DB check by patching it in the health_monitor module
#     # (not in database module, since it's imported directly)
#     def raise_error(*args, **kwargs):
#         raise Exception('dbfail')
    
#     monkeypatch.setattr('src.health_monitor.get_db', raise_error)
#     db_health = monitor.check_database_health()
#     assert db_health.status == 'critical'

#     # Simulate boto3 client missing -> S3 unknown
#     # Force check_s3_health to raise by monkeypatching boto3.client
#     monkeypatch.setattr('boto3.client', lambda *a, **k: (_ for _ in ()).throw(Exception('no s3')))
#     s3 = monitor.check_s3_health()
#     assert s3.status in ('unknown', 'critical')


def test_overall_status_variations(monkeypatch):
    monitor = hm.HealthMonitor()

    # All OK
    monkeypatch.setattr(monitor, 'get_component_health', lambda: [
        hm.ComponentHealth(name='a', status='ok'),
        hm.ComponentHealth(name='b', status='ok')
    ])
    assert monitor.get_overall_status() == 'ok'

    # One degraded
    monkeypatch.setattr(monitor, 'get_component_health', lambda: [
        hm.ComponentHealth(name='a', status='ok'),
        hm.ComponentHealth(name='b', status='degraded')
    ])
    assert monitor.get_overall_status() == 'degraded'

    # Unknown mix
    monkeypatch.setattr(monitor, 'get_component_health', lambda: [
        hm.ComponentHealth(name='a', status='ok'),
        hm.ComponentHealth(name='b', status='unknown')
    ])
    assert monitor.get_overall_status() == 'unknown'

    # Route statistics when no requests
    monitor = hm.HealthMonitor()
    stats = monitor.get_route_statistics()
    assert stats['total_requests'] == 0
    assert stats['success_rate'] == 0


def test_github_and_hf_api_health(monkeypatch):
    monitor = hm.HealthMonitor()

    class GoodResp:
        status_code = 200
        def json(self):
            return {'rate': {'remaining': 200}}

    class LowResp:
        status_code = 200
        def json(self):
            return {'rate': {'remaining': 10}}

    monkeypatch.setattr('requests.get', lambda *a, **k: GoodResp())
    gh = monitor.check_github_api_health()
    assert gh.status == 'ok'

    monkeypatch.setattr('requests.get', lambda *a, **k: LowResp())
    gh2 = monitor.check_github_api_health()
    assert gh2.status == 'degraded'

    # HuggingFace API success and failure
    class HFGood:
        status_code = 200
    class HFBad:
        status_code = 500

    monkeypatch.setattr('requests.get', lambda *a, **k: HFGood())
    hf = monitor.check_huggingface_api_health()
    assert hf.status == 'ok'

    monkeypatch.setattr('requests.get', lambda *a, **k: HFBad())
    hf2 = monitor.check_huggingface_api_health()
    assert hf2.status == 'degraded'
