import pytest
from pathlib import Path
from src.base import parse_url_file, HFModelURL, HFDatasetURL, CodeRepoURL

def test_parse_single_model(tmp_path: Path) -> None:
    file = tmp_path / "urls.txt"
    file.write_text(",,https://huggingface.co/bert-base-uncased\n")
    models = parse_url_file(file)
    assert isinstance(models[0], HFModelURL)
    assert models[0].url.endswith("bert-base-uncased")

def test_parse_with_code_and_dataset(tmp_path: Path) -> None:
    file = tmp_path / "urls.txt"
    file.write_text("https://github.com/user/repo,https://huggingface.co/datasets/foo,https://huggingface.co/model1\n")
    models = parse_url_file(file)
    m = models[0]
    assert isinstance(m.code[0], CodeRepoURL)
    assert isinstance(m.datasets[0], HFDatasetURL)

def test_parse_skips_missing_model(tmp_path: Path) -> None:
    file = tmp_path / "urls.txt"
    file.write_text("https://github.com/user/repo,https://huggingface.co/datasets/foo,\n")
    models = parse_url_file(file)
    assert models == []

def test_parse_deduplicates_datasets(tmp_path: Path) -> None:
    file = tmp_path / "urls.txt"
    file.write_text(
        "repo1,datasetA,modelA\n"
        "repo2,datasetA,modelB\n"
    )
    models = parse_url_file(file)
    assert len(models) == 2
    total_datasets = sum(len(m.datasets) for m in models)
    assert total_datasets == 1

def test_parse_file_not_found() -> None:
    with pytest.raises(FileNotFoundError):
        parse_url_file(Path("nonexistent.txt"))
