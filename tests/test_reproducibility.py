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
    assert "AutoModel" in code
    assert "from_pretrained" in code
    
    # Test with no code block
    readme_no_code = "# Model\n\nThis is text only."
    code = metric._extract_demo_code(readme_no_code)
    assert code == ""


# def test_is_minor_issue():
#     metric = ReproducibilityMetric()
    
#     # Minor issues (fixable)
#     assert metric._is_minor_issue("ModuleNotFoundError: No module named 'torch'")
#     assert metric._is_minor_issue("ImportError: cannot import name 'AutoModel'")
#     assert metric._is_minor_issue("FileNotFoundError: [Errno 2] No such file")
    
#     # Major issues (fundamental problems)
#     assert not metric._is_minor_issue("SyntaxError: invalid syntax")
#     assert not metric._is_minor_issue("IndentationError: unexpected indent")
#     assert not metric._is_minor_issue("TypeError: unsupported operand")
    
#     # Both indicators - major takes precedence
#     assert not metric._is_minor_issue(
#         "ModuleNotFoundError followed by SyntaxError: invalid syntax"
#     )


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


# def test_compute_with_demo_code(monkeypatch):
#     """Test with mocked code execution."""
#     metric = ReproducibilityMetric()
    
#     # Mock successful execution
#     def mock_run_safe(code):
#         return True, "Success output"
    
#     monkeypatch.setattr(metric, "_run_code_safely", mock_run_safe)
    
#     metadata = {
#         "hf_metadata": {
#             "readme_text": """
# ```python
#             print("Hello World")
# ```
#             """
#         }
#     }
    
#     result = metric.compute(metadata)
#     assert result.value == 1.0
#     assert "successfully" in result.details["reason"].lower()
