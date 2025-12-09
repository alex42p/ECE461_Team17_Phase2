from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import List, Set, Optional

@dataclass
class UrlItem:
    """Abstract base representation of a URL (category + raw string)."""
    url: str
    category: str


@dataclass
class HFDatasetURL(UrlItem):
    def __init__(self, url: str):
        super().__init__(url, "DATASET")


@dataclass
class CodeRepoURL(UrlItem):
    def __init__(self, url: str):
        super().__init__(url, "CODE")


@dataclass
class HFModelURL(UrlItem):
    datasets: List[HFDatasetURL]
    code: List[CodeRepoURL]

    def __init__(self, url: str,
                 datasets: Optional[List[HFDatasetURL]] = None,
                 code: Optional[List[CodeRepoURL]] = None):
        super().__init__(url, "MODEL")
        self.datasets = datasets or []
        self.code = code or []


def parse_url_file(path: Path) -> List[HFModelURL]:
    """
    Parse a text file where each line = code, dataset, model.
    Code and dataset may be empty. Models are required.
    Tracks datasets seen so far.
    """
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    models: List[HFModelURL] = []
    seen_datasets: Set[str] = set()

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            # split into up to 3 fields
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 3:
                continue  # skip malformed line

            code_raw, dataset_raw, model_raw = parts[:3]

            if not model_raw:
                continue  # must have a model

            # wrap optional fields
            code_objs = [CodeRepoURL(code_raw)] if code_raw else []
            dataset_objs = []

            if dataset_raw and dataset_raw not in seen_datasets:
                dataset_objs = [HFDatasetURL(dataset_raw)]
                seen_datasets.add(dataset_raw)

            # build model
            model = HFModelURL(
                model_raw,
                datasets=dataset_objs,
                code=code_objs
            )
            models.append(model)

    return models
