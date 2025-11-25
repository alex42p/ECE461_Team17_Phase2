import subprocess
import importlib
import types
import pytest
from src.reproducibility import ReproducibilityMetric


def test_reproducibility_metric_init():
    metric = ReproducibilityMetric()
    assert metric.name == "reproducibility"
    assert metric.TIMEOUT_SECONDS == 120


def test_extract_demo_code():
    metric = ReproducibilityMetric()
    
    # Test with valid code block
    readme = """
    # Model
```python
    from transformers import AutoModel
    model = AutoModel.from_pretrained("bert-base-uncased")
    print(model)
```
    
    More text here.
    """
    code = metric._extract_demo_code(readme)
    assert any("AutoModel" in codeblock for codeblock in code)
    assert any("from_pretrained" in codeblock for codeblock in code)
    
    # Test with no code block
    readme_no_code = "# Model\n\nThis is text only."
    code = metric._extract_demo_code(readme_no_code)
    assert code == []

def test_compute_no_demo_code():
    metric = ReproducibilityMetric()
    
    metadata = {
        "hf_metadata": {
            "readme_text": "# Model\n\nNo code here."
        }
    }
    
    result = metric.compute(metadata)
    assert result.value == 0.0
    assert result.name == "reproducibility"
    assert "No demo code found" in result.details["reason"]


def test_clean_code_block_prompts_and_output():
    metric = ReproducibilityMetric()

    raw = ">>> print(1)\n... print(2)\nSome output\n"
    cleaned = metric._clean_code_block(raw)
    assert 'print(1)' in cleaned and 'print(2)' in cleaned

    raw2 = "import os\nThis is output\nprint('hi')"
    cleaned2 = metric._clean_code_block(raw2)
    assert 'import os' in cleaned2
    assert 'This is output' not in cleaned2


def test_run_code_safely_and_is_minor_issue(monkeypatch):
    metric = ReproducibilityMetric()

    # Simulate successful run
    fake = types.SimpleNamespace(returncode=0, stdout='ok', stderr='')
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: fake)
    ok, out = metric._run_code_safely("print('hi')")
    assert ok is True
    assert 'ok' in out

    # Simulate timeout
    def raise_to(*a, **k):
        raise subprocess.TimeoutExpired(cmd='python', timeout=1)

    monkeypatch.setattr(subprocess, 'run', raise_to)
    ok2, out2 = metric._run_code_safely("print('x')")
    assert ok2 is False
    assert 'timed out' in out2.lower()

    # is_minor_issue
    assert metric._is_minor_issue('ModuleNotFoundError: No module named torch')
    assert not metric._is_minor_issue('SyntaxError: invalid syntax')


mod = importlib.import_module('src.reviewedness')
ReviewednessMetric = getattr(mod, 'ReviewednessMetric')


def test_compute_with_mocked_fetch(monkeypatch):
    m = ReviewednessMetric()
    # Provide repo metadata so compute proceeds
    metadata = {'repo_metadata': {'repo_url': 'https://github.com/owner/repo'}}

    # Mock _fetch_pr_stats to return some numbers
    monkeypatch.setattr(m, '_fetch_pr_stats', lambda owner, repo: (5, 20))

    res = m.compute(metadata)
    assert 0.0 <= res.value <= 1.0
    assert 'pr_commits' in res.details or 'review_percentage' in res.details


def test_fetch_pr_stats_handles_graphql_error(monkeypatch):
    m = ReviewednessMetric()
    # Ensure token is present
    m.github_token = 'fake'

    class FakeResp:
        status_code = 500
        def json(self):
            return {}

    monkeypatch.setattr('requests.post', lambda *a, **k: FakeResp())

    with pytest.raises(Exception):
        m._fetch_pr_stats('o', 'r')
