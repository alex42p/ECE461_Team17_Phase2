import importlib
from src.tree_score import TreeScoreMetric


def test_extract_parent_models_from_siblings_and_readme():
    m = TreeScoreMetric()
    metadata = {
        'hf_metadata': {
            'siblings': [
                {'rfilename': 'config.json', 'data': {'_name_or_path': 'owner/parent-model'}},
            ],
            'readme_text': 'This is based on owner/other-parent and also mentions opt-1.3b'
        }
    }
    parents = m._extract_parent_models(metadata)
    assert 'owner/parent-model' in parents
    assert 'owner/other-parent' in parents or any('opt-1.3b' in p for p in parents)


def test_extract_parent_models_from_config_and_tokens():
    m = TreeScoreMetric()
    metadata = {
        'config': {
            '_name_or_path': ['org/one', 'org/two'],
            'model_name': 'opt-1.3b',
            'some_field': 'based on owner/third-model'
        },
        'hf_metadata': {}
    }
    parents = m._extract_parent_models(metadata)
    assert 'org/one' in parents or 'org/two' in parents
    assert any('opt-1.3b' in p for p in parents)


def test_get_parent_score_tries_name_only(monkeypatch):
    m = TreeScoreMetric()
    calls = []
    # emulate search_by_regex returning empty until name-only match
    def search_by_regex(pat):
        calls.append(pat)
        # return a match if the token 'parent-model' appears anywhere (escaped or not)
        if 'parent-model' in pat.replace('\\', ''):
            return [{'scores': {'net_score': {'value': 0.4}}}]
        return []

    m.storage = type('S', (), {'search_by_regex': staticmethod(search_by_regex)})
    val = m._get_parent_score('org/parent-model')
    assert val == 0.4
    assert len(calls) >= 1


def test_compute_no_parents():
    m = TreeScoreMetric()
    res = m.compute({})
    assert res.value == 0.0
    assert 'reason' in res.details


def test_get_parent_score_and_compute_with_parents(monkeypatch):
    m = TreeScoreMetric()

    # storage.search_by_regex will return a package with net_score
    def search_by_regex(pat):
        if pat:  # return one package
            return [{'scores': {'net_score': {'value': 0.6}}}]
        return []

    m.storage = type('S', (), {'search_by_regex': staticmethod(search_by_regex)})
    metadata = {'hf_metadata': {'readme_text': 'mentions owner/parent-model'}}
    res = m.compute(metadata)
    # parent exists and score is 0.6 -> tree score should be 0.6
    assert abs(res.value - 0.6) < 1e-6


def test_get_parent_score_handles_circular(monkeypatch):
    m = TreeScoreMetric()
    m.storage = type('S', (), {'search_by_regex': staticmethod(lambda p: [{'scores': {'net_score': {'value': 0.5}}}] )})
    # set artifact_id to be same as parent, to trigger circular protection
    res = m.compute({'artifact_id': 'owner/parent-model', 'hf_metadata': {'readme_text': 'owner/parent-model'}})
    # circular dependency -> no evaluated parents -> value 0.0
    assert res.value == 0.0
