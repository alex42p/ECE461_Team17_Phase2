import pytest
from types import SimpleNamespace

from src.huggingface import (
    extract_repo_id,
    extract_dataset_id,
    fetch_repo_metadata,
    fetch_dataset_metadata,
)
from src.entities import HFModel
from src.base import HFModelURL

class FakeResp:
    def __init__(self, status, payload=None, text=''):
        self.status_code = status
        self._payload = payload or {}
        self.text = text
    def json(self):
        return self._payload


def test_extract_repo_id_good_and_bad():
    assert extract_repo_id('https://huggingface.co/google/bert') == 'google/bert'
    with pytest.raises(ValueError):
        extract_repo_id('https://huggingface.co/google')

    # dataset extractor
    assert extract_dataset_id('https://huggingface.co/datasets/glue') == 'glue'
    assert extract_dataset_id('https://huggingface.co/datasets/org/ds') == 'org/ds'
    with pytest.raises(ValueError):
        extract_dataset_id('https://huggingface.co/models/google/bert')


def test_fetch_repo_metadata_parses_and_sets_model(monkeypatch, tmp_path):
    url = 'https://huggingface.co/org/model'
    model = HFModel(HFModelURL(url))

    # First call to API models endpoint
    model_payload = {
        'license': 'N/A',
        'usedStorage': 1024*1024*3,  # 3 MB
        'datasets': [],
        'siblings': [{'rfilename': 'config.json'}, {'rfilename': 'README.md'}],
        'downloads': 1234,
        'downloadsLastMonth': 12,
        'likes': 10,
        'stars': 2,
        'description': 'desc',
        'tags': ['a','b'],
        'author': 'Org'
    }

    def fake_get(url, timeout=None, params=None):
        if url.endswith('/api/models/org/model'):
            return FakeResp(200, model_payload)
        if url.endswith('/raw/main/README.md'):
            # return README that contains license: line
            return FakeResp(200, text='license: MIT\nSome text')
        # fallback
        return FakeResp(404)

    monkeypatch.setattr('src.huggingface.requests.get', fake_get)

    metadata = fetch_repo_metadata(model)
    assert metadata['repo_id'] == 'org/model'
    assert 'readme_text' in metadata
    assert metadata['license'] == 'MIT' or metadata['license'] == 'N/A' or isinstance(metadata['license'], str)
    assert model.metadata == metadata


def test_fetch_dataset_metadata(monkeypatch):
    dataset_url = 'https://huggingface.co/datasets/org/ds'
    payload = {
        'license': 'MIT',
        'cardData': {'size': 42},
        'siblings': [{'rfilename': 'file1'}],
        'downloads': 100,
        'likes': 5,
        'lastModified': '2022-01-01T00:00:00'
    }

    def fake_get(url, timeout=None, params=None):
        if '/api/datasets/' in url:
            return FakeResp(200, payload)
        if '/raw/main/README.md' in url:
            return FakeResp(200, text='readme')
        return FakeResp(404)

    monkeypatch.setattr('src.huggingface.requests.get', fake_get)
    meta = fetch_dataset_metadata(dataset_url)
    assert meta['repo_id'] == 'org/ds'
    assert meta['size_mb'] == 42
    assert isinstance(meta['files'], list)

