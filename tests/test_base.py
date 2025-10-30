import pytest
from pathlib import Path
from src.base import HFModelURL, HFDatasetURL, CodeRepoURL, parse_url_file

def test_hf_model_url_init():
    url = "https://huggingface.co/bert-base-uncased"
    model = HFModelURL(url)
    assert model.url == url
    assert model.category == "MODEL"
    assert model.datasets == []
    assert model.code == []

def test_hf_model_url_with_dataset_and_code():
    model_url = "https://huggingface.co/bert-base-uncased"
    dataset_url = "https://huggingface.co/datasets/glue"
    code_url = "https://github.com/google/bert"
    
    dataset = HFDatasetURL(dataset_url)
    code = CodeRepoURL(code_url)
    model = HFModelURL(model_url, datasets=[dataset], code=[code])
    
    assert model.url == model_url
    assert len(model.datasets) == 1
    assert model.datasets[0].url == dataset_url
    assert len(model.code) == 1
    assert model.code[0].url == code_url

def test_parse_url_file(tmp_path):
    # Create a temporary file with test URLs
    content = """https://github.com/org/repo,https://huggingface.co/datasets/test,https://huggingface.co/model1
,https://huggingface.co/datasets/test2,https://huggingface.co/model2
https://github.com/org/repo2,,https://huggingface.co/model3"""
    
    test_file = tmp_path / "test_urls.txt"
    test_file.write_text(content)
    
    models = parse_url_file(test_file)
    assert len(models) == 3
    
    # Test first model
    assert models[0].url == "https://huggingface.co/model1"
    assert len(models[0].datasets) == 1
    assert models[0].datasets[0].url == "https://huggingface.co/datasets/test"
    assert len(models[0].code) == 1
    
    # Test second model (no code URL)
    assert models[1].url == "https://huggingface.co/model2"
    assert len(models[1].datasets) == 1
    assert len(models[1].code) == 0
    
    # Test third model (no dataset URL)
    assert models[2].url == "https://huggingface.co/model3"
    assert len(models[2].datasets) == 0
    assert len(models[2].code) == 1

def test_parse_url_file_empty(tmp_path):
    test_file = tmp_path / "empty.txt"
    test_file.write_text("")
    models = parse_url_file(test_file)
    assert len(models) == 0

def test_parse_url_file_missing():
    with pytest.raises(FileNotFoundError):
        parse_url_file(Path("nonexistent.txt"))

def test_parse_url_file_malformed(tmp_path):
    # Test with malformed lines
    content = """invalid_line
https://github.com/org/repo
,https://huggingface.co/datasets/test,https://huggingface.co/model1"""
    
    test_file = tmp_path / "malformed.txt"
    test_file.write_text(content)
    
    models = parse_url_file(test_file)
    assert len(models) == 1  # Only the valid line should be parsed