"""
TreeScore metric - average quality score of parent models in lineage graph.
"""
# mypy: ignore-errors

import time
import re
from typing import Any, Dict, Set, Optional
from metric import Metric, MetricResult
import logging
from pathlib import Path


class TreeScoreMetric(Metric):
    """
    Calculate average net_score of all parent models in the dependency tree.
    Uses lineage information from config.json.
    """
    
    def __init__(self, storage=None):
        super().__init__()
        self.storage = storage  # Injected by app.py
        self._visited: Set[str] = set()  # Prevent circular dependencies
        # Per-metric logger setup
        self.logger = logging.getLogger(self.name)
        self.logger.setLevel(logging.DEBUG)
        try:
            root_dir = Path(__file__).resolve().parents[1]
        except Exception:
            root_dir = Path('.')
        logs_dir = root_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_file = logs_dir / f"{self.name}.log"
        if not any(isinstance(h, logging.FileHandler) and h.baseFilename == str(log_file) for h in self.logger.handlers):
            fh = logging.FileHandler(str(log_file), mode='w')
            fh.setLevel(logging.DEBUG)
            fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
            fh.setFormatter(fmt)
            self.logger.addHandler(fh)
        self.logger.info("Initialized TreeScoreMetric (storage_present=%s)", bool(self.storage))
    
    @property
    def name(self) -> str:
        return "tree_score"
    
    def compute(self, metadata: Dict[str, Any]) -> MetricResult:
        t0 = time.time()
        self.logger.debug("compute called")
        
        try:
            # Get current model's artifact_id (if available)
            artifact_id = metadata.get("artifact_id")
            
            # Parse parent models from config.json
            parents = self._extract_parent_models(metadata)
            self.logger.info("Found parent models: %s", parents)

            if not parents:
                self.logger.info("No parent models found in metadata/config")
                return MetricResult(
                    name=self.name,
                    value=0.0,
                    details={"reason": "No parent models found"},
                    latency_ms=max(1, int((time.time() - t0) * 1000))
                )
            
            # Fetch scores for parent models
            parent_scores = []
            self._visited.clear()
            if artifact_id:
                self._visited.add(artifact_id)
            
            for parent_id in parents:
                score = self._get_parent_score(parent_id)
                if score is not None:
                    parent_scores.append(score)
            
            if not parent_scores:
                tree_score = 0.0
                details: Dict[str, Any] = {"reason": "Could not fetch parent scores"}
            else:
                tree_score = sum(parent_scores) / len(parent_scores)
                details: Dict[str, Any] = {
                    "num_parents": len(parents),
                    "evaluated_parents": len(parent_scores),
                    "parent_scores": parent_scores
                }
                self.logger.info("Computed tree_score=%s from %s evaluated parents", tree_score, len(parent_scores))
            
            return MetricResult(
                name=self.name,
                value=round(tree_score, 3),
                details=details,
                latency_ms=max(1, int((time.time() - t0) * 1000))
            )
            
        except Exception as e:
            self.logger.exception("Unhandled exception in compute: %s", e)
            return MetricResult(
                name=self.name,
                value=0.0,
                details={"error": str(e)},
                latency_ms=max(1, int((time.time() - t0) * 1000))
            )
    
    def _extract_parent_models(self, metadata: Dict[str, Any]) -> list[str]:
        """
        Extract parent model IDs from config.json.
        
        Common fields in HuggingFace config.json:
        - _name_or_path: base model name
        - base_model_name_or_path: fine-tuning parent
        - model_type: architecture family
        """
        parents = []
        common_fields = ["_name_or_path", "base_model_name_or_path", "model_type", "model_name", "parent_model"]

        # Helper to add candidates (strings, lists, dicts)
        def add_candidate(val: Any) -> None:
            if not val:
                return
            if isinstance(val, str):
                candidates = [val]
            elif isinstance(val, (list, tuple)):
                candidates = [str(v) for v in val if v]
            elif isinstance(val, dict):
                # try common nested keys
                candidates = []
                for k in ("_name_or_path", "model_name", "name", "base_model_name_or_path"):
                    if k in val and isinstance(val[k], str):
                        candidates.append(val[k])
            else:
                candidates = [str(val)]

            for c in candidates:
                c = c.strip()
                if c:
                    parents.append(c)

        # Try to get config.json from hf_metadata siblings first
        hf_metadata = metadata.get("hf_metadata", {})
        siblings = hf_metadata.get("siblings", [])
        config_data = None
        for sibling in siblings:
            if sibling.get("rfilename") in ("config.json", "model_config.json", "config"):
                config_data = sibling.get("data", {})
                self.logger.debug("Found config.json-like sibling: %s", sibling.get("rfilename"))
                break

        # Fallbacks: direct config fields in metadata
        if config_data is None:
            config_data = metadata.get("config") or hf_metadata.get("config") or metadata.get("model_info") or {}

        # Extract from common fields in config
        if isinstance(config_data, dict):
            for field in common_fields:
                add_candidate(config_data.get(field))

            # Also scan all string values in config_data for model-like tokens
            for k, v in config_data.items():
                if isinstance(v, str):
                    # look for owner/model patterns or tokens that look like model names
                    matches = re.findall(r"[\w-]+/[\w-]+|[a-zA-Z0-9_\-]+(?:-[0-9][\w\-]*)?", v)
                    for m in matches:
                        # Basic heuristic: accept owner/model or tokens with a dash+digit (e.g., opt-1.3b)
                        if "/" in m or re.search(r"-\d", m):
                            parents.append(m)

        # Parse readme text (if present) for owner/model mentions
        readme = hf_metadata.get("readme_text", "") or metadata.get("readme_text", "") or ""
        readme_lower = readme.lower()
        # Common phrases that may indicate parent references
        parent_patterns = [
            "base model:",
            "fine-tuned from",
            "trained from",
            "parent model:",
            "derived from",
            "based on"
        ]

        # Always look for explicit owner/model occurrences in the README
        readme_matches = re.findall(r"[\w-]+/[\w-]+", readme)
        parents.extend(readme_matches)

        for pattern in parent_patterns:
            if pattern in readme_lower:
                idx = readme_lower.find(pattern)
                snippet = readme[idx:idx+300]
                matches = re.findall(r"[\w-]+/[\w-]+|[a-zA-Z0-9_\-]+(?:-[0-9][\w\-]*)?", snippet)
                for m in matches:
                    if "/" in m or re.search(r"-\d", m):
                        parents.append(m)
                break

        # Normalize and dedupe
        cleaned = []
        for p in parents:
            p = p.strip()
            if p:
                cleaned.append(p)

        return list(dict.fromkeys(cleaned))  # preserve order, remove duplicates
    
    def _get_parent_score(self, parent_id: str) -> Optional[float]:
        """
        Fetch net_score for parent model.
        Prevents circular dependencies using _visited set.
        """
        if not self.storage:
            return None

        if parent_id in self._visited:
            return None  # Circular dependency

        self._visited.add(parent_id)

        try:
            # Try multiple search heuristics to find the parent in storage
            tried_patterns = []
            parent_packages = []

            # 1) exact (anchored)
            tried_patterns.append(f"^{re.escape(parent_id)}$")
            parent_packages = self.storage.search_by_regex(tried_patterns[-1])

            # 2) plain substring (unanchored)
            if not parent_packages:
                tried_patterns.append(re.escape(parent_id))
                parent_packages = self.storage.search_by_regex(tried_patterns[-1])

            # 3) if owner/name, try name-only
            if not parent_packages and "/" in parent_id:
                name_only = parent_id.split("/", 1)[1]
                tried_patterns.append(f"^{re.escape(name_only)}$")
                parent_packages = self.storage.search_by_regex(tried_patterns[-1])
                if not parent_packages:
                    tried_patterns.append(re.escape(name_only))
                    parent_packages = self.storage.search_by_regex(tried_patterns[-1])

            # 4) try lowercase variants
            if not parent_packages:
                tried_patterns.append(re.escape(parent_id.lower()))
                parent_packages = self.storage.search_by_regex(tried_patterns[-1])

            if not parent_packages:
                self.logger.debug("No storage results for parent '%s' (patterns tried: %s)", parent_id, tried_patterns)
                return None

            # Get the first candidate (storage should ideally return most relevant first)
            parent = parent_packages[0]
            net_score = parent.get("scores", {}).get("net_score", {}).get("value")
            self.logger.debug("Fetched parent %s net_score=%s (using pattern %s)", parent_id, net_score, tried_patterns[0] if tried_patterns else None)
            return float(net_score) if net_score is not None else None

        except Exception:
            self.logger.exception("Error fetching parent score for %s", parent_id)
            return None