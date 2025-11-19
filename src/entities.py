from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from base import HFModelURL
from metric import MetricResult
from urllib.parse import urlparse

@dataclass
class HFModel():
    def __init__(self, model_url: HFModelURL):
        self.model_url = model_url
        self.repo_id = self.extract_repo_id()
        self.metadata: dict[str, Any] = {}
        self.metric_scores: dict[str, MetricResult] = {}

    @property
    def name(self) -> str:
        """Short model name (last part of repo_id)."""
        return self.repo_id.split("/")[-1]

    def extract_repo_id(self) -> str:
        """Extract org/model from Hugging Face URL."""
        path: str = urlparse(self.model_url.url).path.strip("/")
        # e.g. "google-bert/bert-base-uncased" or "openai/whisper-tiny"
        parts = path.split("/")
        if len(parts) >= 2:
            return f"{parts[0]}/{parts[1]}"
        return path  # fallback
    
    def extract_model_name(self) -> str:
        """Extract the short model name from the HF URL."""
        parts: list[str] = urlparse(self.model_url.url).path.strip("/").split("/")
        if "tree" in parts:
            idx = parts.index("tree")
            if idx > 0:
                return parts[idx - 1]
        return parts[-1] if parts else self.model_url.url

    def add_results(self, metric_results: list[MetricResult]) -> None:
        self.metric_scores.update({r.name: r for r in metric_results})

