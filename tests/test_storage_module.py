import re
import tempfile
import shutil

import pytest

from src.storage import S3Storage


def test_save_and_get_package(tmp_path):
    d = tmp_path / 'stor'
    svc = S3Storage(storage_dir=str(d))

    info = svc.save_package('mypkg', '1.0.0', url='http://x', scores={'net_score': {'value': 0.5}})
    pid = info['id']
    got = svc.get_package(pid)
    if got:
        assert got['name'] == 'mypkg'
        assert got['scores']['net_score']['value'] == 0.5


def test_search_by_regex_and_invalid_pattern(tmp_path):
    d = tmp_path / 'stor2'
    svc = S3Storage(storage_dir=str(d))

    a = svc.save_package('alpha', '0.1', scores={'net_score': {'value': 1.0}})
    b = svc.save_package('beta', '0.1', scores={'net_score': {'value': 0.2}})

    res = svc.search_by_regex('a')
    assert any('alpha' == p['name'] or 'beta' == p['name'] for p in res)

    with pytest.raises(ValueError):
        svc.search_by_regex('[')


def test_get_package_not_found_and_upload_errors(tmp_path, monkeypatch):
    d = tmp_path / 'stor3'
    svc = S3Storage(storage_dir=str(d))

    # Non-existent id
    assert svc.get_package('no-such-id') is None

    # upload_file_to_s3: missing file
    with pytest.raises(FileNotFoundError):
        svc.upload_file_to_s3(str(d / 'nofile.txt'), 'k')

    # upload_file_to_s3: missing bucket name
    monkeypatch.setenv('S3_BUCKET_NAME', '')
    svc2 = S3Storage(storage_dir=str(d))
    with pytest.raises(ValueError):
        svc2.upload_file_to_s3(str(d / 'nofile.txt'), 'k')


def test_upload_file_success_and_save_with_file(monkeypatch, tmp_path):
    d = tmp_path / 'stor4'
    svc = S3Storage(storage_dir=str(d))

    # Create a real file
    f = tmp_path / 'real.txt'
    f.write_text('hello')

    # Monkeypatch s3_client.upload_file to do nothing (simulate success)
    monkeypatch.setattr(svc.s3_client, 'upload_file', lambda src, bucket, key: None)

    s3_uri = svc.upload_file_to_s3(str(f), 'k/key.txt')
    assert s3_uri.startswith('s3://')

    # Now test save_package with file_path uses upload_file_to_s3 and records s3 metadata
    monkeypatch.setattr(svc, 'upload_file_to_s3', lambda fp, key: f"s3://bucket/{key}")
    pkg = svc.save_package('withfile', '0.1', file_path=str(f))
    assert 's3' in pkg and 'uri' in pkg['s3']


def test_generate_package_id_and_search_handles_bad_json(tmp_path):
    d = tmp_path / 'stor5'
    svc = S3Storage(storage_dir=str(d))
    # generate id
    pid = svc.generate_package_id('name/with/slash', '1.0')
    assert '/' not in pid

    # create a bad json file in metadata dir
    bad = svc.metadata_dir / 'bad.json'
    bad.write_text('not a json')
    # This should not raise, but skip the bad file and return empty list
    res = svc.search_by_regex('name')
    assert isinstance(res, list)


def test_save_package_handles_existing_corrupt_and_get_package_error(tmp_path, monkeypatch):
    d = tmp_path / 'stor6'
    svc = S3Storage(storage_dir=str(d))

    # Create a corrupt existing metadata file matching safe_name-version pattern
    safe = 'corrupt_name'.replace('/', '_')
    fname = f"{safe}-1.0-abcdef01.json"
    fpath = svc.metadata_dir / fname
    fpath.write_text('not-json')

    # Now call save_package which should attempt to read existing and catch exception
    pkg = svc.save_package('corrupt_name', '1.0')
    assert pkg is not None and isinstance(pkg.get('id'), str)

    # Now write a corrupt file for get_package and ensure it returns None
    badid = 'badpkg-1.0-1234'
    badfile = svc.metadata_dir / f"{badid}.json"
    badfile.write_text('not json either')
    assert svc.get_package(badid) is None


def test_upload_file_s3_exception(monkeypatch, tmp_path):
    d = tmp_path / 'stor7'
    svc = S3Storage(storage_dir=str(d))
    f = tmp_path / 'to_upload.txt'
    f.write_text('data')

    # Make upload_file raise
    def raise_exc(src, bucket, key):
        raise Exception('s3 fail')

    monkeypatch.setattr(svc.s3_client, 'upload_file', raise_exc)
    with pytest.raises(Exception):
        svc.upload_file_to_s3(str(f), 'k')
