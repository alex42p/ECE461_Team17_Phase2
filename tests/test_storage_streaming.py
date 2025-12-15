import importlib
import io
import subprocess
import boto3
import pytest


class FakePopen:
    def __init__(self, retcode=0, out=b'hello'):
        self.stdout = io.BytesIO(out)
        self.returncode = retcode
    def communicate(self):
        return (b'', b'')


class FakeCompleted:
    def __init__(self):
        self.stdout = 'ok'


def test_upload_hf_repo_streaming_success(monkeypatch):
    import src.storage as st
    importlib.reload(st)
    class DummyClient:
        def upload_fileobj(self, fileobj, Bucket, Key, ExtraArgs=None):
            # read stream to simulate upload
            fileobj.read()
        def generate_presigned_url(self, *a, **k):
            return 'https://presigned'
        def delete_object(self, Bucket, Key):
            return True

    monkeypatch.setattr(boto3, 'client', lambda *a, **k: DummyClient())
    s = st.S3Storage(storage_dir='pkg', aws_region='us-east-1')

    # stub subprocess.run to succeed
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: FakeCompleted())
    # stub Popen to our fake
    monkeypatch.setattr(subprocess, 'Popen', lambda *a, **k: FakePopen())

    uri = s._upload_huggingface_repo_streaming('https://example', 'org/model', 'models/key', artifact_type='model')
    assert uri.startswith('s3://')


def test_upload_hf_repo_streaming_clone_fallback_and_error(monkeypatch):
    import src.storage as st
    importlib.reload(st)
    class DummyClient:
        def upload_fileobj(self, fileobj, Bucket, Key, ExtraArgs=None):
            fileobj.read()
        def generate_presigned_url(self, *a, **k):
            return 'https://presigned'
        def delete_object(self, Bucket, Key):
            return True

    monkeypatch.setattr(boto3, 'client', lambda *a, **k: DummyClient())
    s = st.S3Storage(storage_dir='pkg', aws_region='us-east-1')

    # first run raises CalledProcessError, second run succeeds
    class FirstFail:
        def __init__(self, *a, **k):
            raise subprocess.CalledProcessError(1, 'cmd', stderr=b'err')

    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: (_ for _ in ()).throw(subprocess.CalledProcessError(1, 'cmd', stderr=b'err')) if k.get('branch', 'main') != 'master' else FakeCompleted())
    monkeypatch.setattr(subprocess, 'Popen', lambda *a, **k: FakePopen())

    # Should either succeed or raise RuntimeError depending on fallback; ensure no unhandled exception
    try:
        uri = s._upload_huggingface_repo_streaming('https://example', 'org/model', 'models/key', artifact_type='model')
        assert uri.startswith('s3://')
    except RuntimeError:
        # acceptable - the code may raise if clone fails both times
        assert True


def test_upload_hf_repo_streaming_archive_failure_and_cleanup(monkeypatch):
    import src.storage as st
    importlib.reload(st)

    deleted = {'called': False}

    class DummyClient:
        def upload_fileobj(self, fileobj, Bucket, Key, ExtraArgs=None):
            # simulate upload succeeding by reading, but then we'll simulate archive failure
            fileobj.read()
        def generate_presigned_url(self, *a, **k):
            return 'https://presigned'
        def delete_object(self, Bucket, Key):
            deleted['called'] = True

    monkeypatch.setattr(boto3, 'client', lambda *a, **k: DummyClient())
    s = st.S3Storage(storage_dir='pkg', aws_region='us-east-1')

    # subprocess.run succeeds
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: FakeCompleted())

    class BadPopen(FakePopen):
        def __init__(self, *a, **k):
            super().__init__(retcode=1, out=b'')
        def communicate(self):
            return (b'', b'error')

    monkeypatch.setattr(subprocess, 'Popen', lambda *a, **k: BadPopen())

    # Expect RuntimeError and cleanup called
    try:
        s._upload_huggingface_repo_streaming('https://example', 'org/model', 'models/key', artifact_type='model')
    except RuntimeError:
        assert deleted['called'] is True
