import importlib
import types
import src.reviewedness as reviewedness


def test_compute_no_repo(monkeypatch):
    importlib.reload(reviewedness)
    rm = reviewedness.ReviewednessMetric()
    res = rm.compute({})
    assert res.value == -1.0


def test_parse_github_url():
    importlib.reload(reviewedness)
    rm = reviewedness.ReviewednessMetric()
    owner, repo = rm._parse_github_url('https://github.com/org/repo')
    assert owner == 'org' and repo == 'repo'


def test_fetch_pr_stats_errors_and_counts(monkeypatch):
    importlib.reload(reviewedness)
    rm = reviewedness.ReviewednessMetric()

    # require token
    rm.github_token = None
    try:
        rm._fetch_pr_stats('o', 'r')
    except ValueError:
        pass

    # provide token and simulate non-200 response
    rm.github_token = 'x'

    class BadResp:
        status_code = 500
        def json(self):
            return {}

    monkeypatch.setattr(reviewedness.requests, 'post', lambda *a, **k: BadResp())
    try:
        rm._fetch_pr_stats('o', 'r')
    except Exception:
        pass

    # simulate successful page with nodes and reviews
    class GoodResp:
        status_code = 200
        def __init__(self, data):
            self._data = data
        def json(self):
            return self._data

    data = {
        'data': {
            'repository': {
                'defaultBranchRef': {
                    'target': {
                        'history': {
                            'nodes': [
                                {'associatedPullRequests': {'nodes': [{'reviews': {'totalCount': 1}}]}} ,
                                {'associatedPullRequests': {'nodes': []}}
                            ],
                            'pageInfo': {'hasNextPage': False, 'endCursor': None}
                        }
                    }
                }
            }
        }
    }

    monkeypatch.setattr(reviewedness.requests, 'post', lambda *a, **k: GoodResp(data))
    pr, total = rm._fetch_pr_stats('o', 'r')
    assert total == 2 and pr == 1
