import boto3
import io
import pytest


class DummyS3Client:
    def __init__(self):
        self.objects = {}

    def generate_presigned_url(self, *a, **k):
        return f"https://s3.fake/{k['Params']['Key']}"

    def upload_fileobj(self, fileobj, Bucket, Key, ExtraArgs=None):
        # read stream to simulate upload
        if hasattr(fileobj, 'read'):
            fileobj.read()
        self.objects[Key] = True

    def get_paginator(self, name):
        class P:
            def __init__(self, objs):
                self._objs = objs
            def paginate(self, **kwargs):
                yield {'Contents': [{'Key': k} for k in self._objs.keys()]}
        return P(self.objects)

    def delete_objects(self, Bucket, Delete):
        for o in Delete.get('Objects', []):
            self.objects.pop(o['Key'], None)
        return {'Deleted': Delete.get('Objects', [])}

    def delete_object(self, Bucket, Key):
        self.objects.pop(Key, None)


def test_generate_package_id_and_folder_and_presigned(monkeypatch):
    import importlib
    import src.storage as st
    importlib.reload(st)
    monkeypatch.setattr(boto3, 'client', lambda *a, **k: DummyS3Client())
    from src.storage import S3Storage

    s = S3Storage(storage_dir='pkg', aws_region='us-east-1')
    pid = s.generate_package_id('org/model')
    assert isinstance(pid, str) and len(pid) == 16

    assert s._get_s3_folder('model') == 'models/'
    assert s._get_s3_folder('dataset') == 'datasets/'
    assert s._get_s3_folder('code') == 'codes/'
    assert s._get_s3_folder(None) == 'models/'

    url = s._generate_presigned_url('bucket', 'key')
    assert url.startswith('https://s3.fake/')

    # simulate presigned generation failure
    class BadClient(DummyS3Client):
        def generate_presigned_url(self, *a, **k):
            raise RuntimeError('boom')

    monkeypatch.setattr(boto3, 'client', lambda *a, **k: BadClient())
    import importlib
    import src.storage as st
    importlib.reload(st)
    s2 = st.S3Storage(storage_dir='pkg', aws_region='us-east-1')
    assert s2._generate_presigned_url('bucket', 'key') is None


def test_save_package_and_clear(monkeypatch):
    import importlib
    import src.storage as st
    importlib.reload(st)
    monkeypatch.setattr(boto3, 'client', lambda *a, **k: DummyS3Client())
    from src.storage import S3Storage

    s = S3Storage(storage_dir='pkg', aws_region='us-west-2')

    # stub internal upload and presigned generation
    monkeypatch.setattr(s, '_upload_huggingface_repo_streaming', lambda *a, **k: 's3://bucket/key')
    monkeypatch.setattr(s, '_generate_presigned_url', lambda *a, **k: 'https://download')

    pkg = s.save_package('org/model', url='https://huggingface.co/org/model', artifact_type='model')
    assert 'metadata' in pkg and 'data' in pkg

    # clear objects (no exception)
    s.clear_all_s3_objects()

    # simulate paginator error
    class BrokenClient(DummyS3Client):
        def get_paginator(self, name):
            raise RuntimeError('paginator fail')

    monkeypatch.setattr(boto3, 'client', lambda *a, **k: BrokenClient())
    importlib.reload(st)
    s3 = st.S3Storage(storage_dir='pkg', aws_region='us-west-2')
    # should not raise
    s3.clear_all_s3_objects()
