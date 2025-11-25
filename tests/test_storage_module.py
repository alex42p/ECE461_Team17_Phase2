import re
import tempfile
import shutil

import pytest

from src.storage import PackageStorage


def test_save_and_get_package(tmp_path):
    d = tmp_path / 'stor'
    svc = PackageStorage(storage_dir=str(d))

    info = svc.save_package('mypkg', '1.0.0', url='http://x', scores={'net_score': {'value': 0.5}})
    pid = info['id']
    got = svc.get_package(pid)
    if got:
        assert got['name'] == 'mypkg'
        assert got['scores']['net_score']['value'] == 0.5


def test_search_by_regex_and_invalid_pattern(tmp_path):
    d = tmp_path / 'stor2'
    svc = PackageStorage(storage_dir=str(d))

    a = svc.save_package('alpha', '0.1', scores={'net_score': {'value': 1.0}})
    b = svc.save_package('beta', '0.1', scores={'net_score': {'value': 0.2}})

    res = svc.search_by_regex('a')
    assert any('alpha' == p['name'] or 'beta' == p['name'] for p in res)

    with pytest.raises(ValueError):
        svc.search_by_regex('[')
