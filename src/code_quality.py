"""
DOCTYPE: Code Quality metric (readability, structure, and maintainability).

This metric inspects Hugging Face model repositories for indicators of good 
software practices, including the presence of a README, config files, training 
scripts, sufficient Python source files, and a clean project structure. It 
aggregates these signals with weighted scores into a final value in [0,1], where 
higher scores reflect better-documented, more maintainable codebases.
"""

import time
from typing import Any, Dict
from metric import MetricResult, Metric
from huggingface_inspect import clone_model_repo, clean_up_cache

class CodeQualityMetric(Metric):
    """
    Computes code quality for Hugging Face model repos based on heuristics:
      - Presence of README.md
      - Presence of config.json
      - Presence of .py files (esp. train.py / run.py)
      - Project cleanliness (few junk files)
    """
    @property
    def name(self) -> str:
        return "code_quality"

    def compute(self, metadata: Dict[str, Any]) -> MetricResult:
        t0 = time.time()
        model_id = metadata["hf_metadata"].get("repo_id", None)
        if not model_id:
            return MetricResult(
                name=self.name,
                value=0.0,
                details={"error": "No model ID found in metadata"},
                latency_ms=0
            )

        # Clone and inspect repo
        model_path = clone_model_repo(model_id)
        score_components = {
            "readme_score": 0.0,
            "config_score": 0.0,
            "training_script_score": 0.0,
            "python_file_score": 0.0,
            "structure_score": 0.0,
        }

        try:
            # 1. README Score
            readme_path = model_path / "README.md"
            if readme_path.exists():
                readme_len = len(readme_path.read_text(encoding="utf-8"))
                score_components["readme_score"] = min(1.0, readme_len / 500.0)  # 500+ chars = 1.0

            # 2. Config Score
            config_path = model_path / "config.json"
            if config_path.exists():
                score_components["config_score"] = 1.0

            # 3. Training Script Score
            for filename in ["train.py", "run.py", "finetune.py"]:
                if (model_path / filename).exists():
                    score_components["training_script_score"] = 1.0
                    break

            # 4. Python Files Score
            py_files = list(model_path.rglob("*.py"))
            score_components["python_file_score"] = min(1.0, len(py_files) / 5.0)  # 5+ files → 1.0

            # 5. Structure Score: penalize if too many random files (>20 files)
            all_files = list(model_path.rglob("*"))
            file_count = len([f for f in all_files if f.is_file()])
            if file_count <= 20:
                score_components["structure_score"] = 1.0
            elif file_count <= 50:
                score_components["structure_score"] = 0.5
            else:
                score_components["structure_score"] = 0.0

            # Final quality = weighted average
            weights = {
                "readme_score": 0.25,
                "config_score": 0.2,
                "training_script_score": 0.2,
                "python_file_score": 0.2,
                "structure_score": 0.15,
            }

            quality = sum(weights[k] * score_components[k] for k in score_components)

            latency = int((time.time() - t0) * 1000)
            return MetricResult(
                name=self.name,
                value=round(quality, 3),
                details={k: round(v, 3) for k, v in score_components.items()},
                latency_ms=latency
            )

        finally:
            clean_up_cache(model_path)
