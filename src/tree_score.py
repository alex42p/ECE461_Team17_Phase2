"""
TreeScore metric - average quality score of parent models in lineage graph.
"""

import time
from typing import Any, Dict, Set, Optional
from metric import Metric, MetricResult


class TreeScoreMetric(Metric):
    """
    Calculate average net_score of all parent models in the dependency tree.
    Uses lineage information from config.json.
    """
    
    def __init__(self, storage=None):
        super().__init__()
        self.storage = storage  # Injected by app.py
        self._visited: Set[str] = set()  # Prevent circular dependencies
    
    @property
    def name(self) -> str:
        return "tree_score"
    
    def compute(self, metadata: Dict[str, Any]) -> MetricResult:
        t0 = time.time()
        
        try:
            # Get current model's artifact_id (if available)
            artifact_id = metadata.get("artifact_id")
            
            # Parse parent models from config.json
            parents = self._extract_parent_models(metadata)
            
            if not parents:
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
            
            return MetricResult(
                name=self.name,
                value=round(tree_score, 3),
                details=details,
                latency_ms=max(1, int((time.time() - t0) * 1000))
            )
            
        except Exception as e:
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
        
        # Try to get config.json from siblings
        hf_metadata = metadata.get("hf_metadata", {})
        siblings = hf_metadata.get("siblings", [])
        
        # Look for config.json reference
        config_file = None
        for sibling in siblings:
            if sibling.get("rfilename") == "config.json":
                config_file = sibling
                break
        
        if not config_file:
            return parents
        
        # For MVP, check if parent model is mentioned in README or metadata
        # In production, you'd download and parse config.json
        readme = hf_metadata.get("readme_text", "")
        
        # Look for common parent model patterns
        parent_patterns = [
            "base model:",
            "fine-tuned from",
            "trained from",
            "parent model:",
            "derived from"
        ]
        
        readme_lower = readme.lower()
        for pattern in parent_patterns:
            if pattern in readme_lower:
                # Extract model name after pattern
                # This is simplified - in production, parse config.json properly
                idx = readme_lower.find(pattern)
                snippet = readme[idx:idx+200]
                # Look for HuggingFace model format (org/model)
                import re
                matches = re.findall(r'[\w-]+/[\w-]+', snippet)
                parents.extend(matches[:3])  # Limit to 3 parents
                break
        
        return list(set(parents))  # Remove duplicates
    
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
            # Search for parent by name
            parent_packages = self.storage.search_by_regex(f"^{parent_id}$")
            
            if not parent_packages:
                return None
            
            # Get most recent version
            parent = parent_packages[0]
            net_score = parent.get("scores", {}).get("net_score", {}).get("value")
            
            return float(net_score) if net_score is not None else None
            
        except Exception:
            return None