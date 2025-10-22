"""
DOCTYPE: Dataset Quality metric (popularity, documentation, and licensing).

This metric evaluates the quality of a dataset hosted on Hugging Face using 
metadata such as downloads, likes, file count, dataset size, readme coverage, 
and license presence. It aggregates these signals with weighted scores to produce 
a final value in [0,1], where higher scores reflect better-documented, more 
popular, and more usable datasets.
"""

from typing import Any
import time
from metric import Metric, MetricResult
from huggingface import fetch_dataset_metadata


class DatasetQualityMetric(Metric):
    """
    Computes dataset quality heuristically based on Hugging Face dataset metadata.
    Factors include:
      - downloads (fallback to likes)
      - likes
      - number of files or tags
      - dataset size (MB, estimated if missing)
      - license presence
      - readme_text coverage
    """

    @property
    def name(self) -> str:
        return "dataset_quality"

    def compute(self, metadata: dict[str, Any]) -> MetricResult:
        t0 = time.time()

        dataset_url = metadata["hf_metadata"].get("dataset_url", "")
        if not dataset_url:
            return MetricResult(
                name=self.name,
                value=0.0,
                details={"error": "Missing dataset URL"},
                latency_ms=0,
            )

        dataset_metadata = fetch_dataset_metadata(dataset_url) or {}

        downloads = dataset_metadata.get("downloads", 0) or 0
        likes = dataset_metadata.get("likes", 0) or 0
        num_files = dataset_metadata.get("num_files", 0) or 0
        size_mb = dataset_metadata.get("size_mb", 0) or 0
        readme_text = dataset_metadata.get("readme_text", "") or ""
        license_str = dataset_metadata.get("license", "unknown") or "unknown"

        # --- Fallbacks ---
        if downloads == 0 and likes > 0:
            downloads = likes * 50  # rough proxy
        if num_files == 0:
            num_files = len(dataset_metadata.get("tags", []))
        if size_mb == 0:
            size_mb = num_files * 10  # rough proxy

        # 1. Popularity Score
        popularity = min(1.0, (downloads / 10000.0) ** 0.25) if downloads else 0.0

        # 2. Like Ratio Score
        like_ratio = likes / downloads if downloads else 0.0
        like_score = min(1.0, like_ratio * 5)

        # 3. File Count Score
        file_score = min(1.0, num_files / 10.0)

        # 4. Size Score
        if size_mb < 1:
            size_score = 0.0
        elif size_mb > 5000:
            size_score = 0.2  # not instantly fail, just penalize
        else:
            size_score = min(1.0, size_mb / 500.0)  # 500MB → 1.0

        # 5. Readme Score
        readme_score = 1.0 if len(readme_text) > 300 else len(readme_text) / 300.0

        # 6. License Score
        license_score = 1.0 if license_str and license_str.lower() != "unknown" else 0.0

        # Weighted aggregation
        weights = {
            "popularity": 0.25,
            "like_score": 0.2,
            "file_score": 0.15,
            "size_score": 0.15,
            "readme_score": 0.15,
            "license_score": 0.1,
        }

        total = (
            weights["popularity"] * popularity +
            weights["like_score"] * like_score +
            weights["file_score"] * file_score +
            weights["size_score"] * size_score +
            weights["readme_score"] * readme_score +
            weights["license_score"] * license_score
        )

        details = {
            "popularity": round(popularity, 3),
            "like_score": round(like_score, 3),
            "file_score": round(file_score, 3),
            "size_score": round(size_score, 3),
            "readme_score": round(readme_score, 3),
            "license_score": round(license_score, 3),
            "downloads": downloads,
            "likes": likes,
            "num_files": num_files,
            "size_mb": size_mb,
            "license": license_str,
        }

        latency = int((time.time() - t0) * 1000)

        return MetricResult(
            name=self.name,
            value=round(total, 3),
            details=details,
            latency_ms=latency,
        )
