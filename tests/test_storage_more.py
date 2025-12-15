import importlib
import boto3


def test_dataset_repo_url_branch_and_clear_errors(monkeypatch):
    import src.storage as st
    importlib.reload(st)

    class ErrClient:
        def __init__(self):
            self.objects = {'k1': True}
        def generate_presigned_url(self, *a, **k):
            return 'https://p'
        def upload_fileobj(self, fileobj, Bucket, Key, ExtraArgs=None):
            fileobj.read()
        def delete_object(self, Bucket, Key):
            return True
        def get_paginator(self, name):
            class P:
                def paginate(self, **kwargs):
                    yield {'Contents': [{'Key': 'k1'}]}
            return P()
        def delete_objects(self, Bucket, Delete):
            return {'Errors': [{'Key': 'k1', 'Message': 'm'}]}

    monkeypatch.setattr(boto3, 'client', lambda *a, **k: ErrClient())
    s = st.S3Storage(storage_dir='pkg', aws_region='us-east-1')

    # dataset artifact_type with hf_token should construct datasets repo URL
    s.hf_token = 'hf'
    # stub subprocess and popen to be benign
    import subprocess
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: type('R', (), {'stdout': 'ok'}))
    import io
    class FakeP:
        def __init__(self):
            self.stdout = io.BytesIO(b'')
            self.returncode = 0
        def communicate(self):
            return (b'', b'')
    monkeypatch.setattr(subprocess, 'Popen', lambda *a, **k: FakeP())

    # should not raise - upload uses dataset branch for repo_url
    s._upload_huggingface_repo_streaming('https://u', 'org/ds', 'datasets/key', artifact_type='dataset')

    # clear_all_s3_objects should handle delete_objects Errors gracefully
    s.clear_all_s3_objects()


def test_generate_and_save_and_presigned(monkeypatch):
    import src.storage as storage
    importlib.reload(storage)
    s = storage.S3Storage(storage_dir='pkg', aws_region='us-east-1')

    # test generate id
    pid = s.generate_package_id('org/model')
    assert isinstance(pid, str) and len(pid) == 16

    # monkeypatch streaming upload to raise and ensure save_package handles it
    monkeypatch.setattr(storage.S3Storage, '_upload_huggingface_repo_streaming', lambda *a, **k: (_ for _ in ()).throw(Exception('boom')))
    monkeypatch.setattr(storage.S3Storage, '_generate_presigned_url', lambda *a, **k: None)
    pkg = s.save_package('org/model', url='https://huggingface.co/org/model', artifact_type='model')
    assert 'metadata' in pkg and pkg['data']['download_url'] is None

    # presigned url generation exception
    class BadClient:
        def generate_presigned_url(self, *a, **k):
            raise Exception('no')
    s.s3_client = BadClient()
    assert s._generate_presigned_url('b', 'k') is None

    # clear_all_s3_objects short-circuit when no bucket
    s.bucket_name = None
    s.clear_all_s3_objects()
