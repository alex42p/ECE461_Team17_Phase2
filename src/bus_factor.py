"""
DOCTYPE: Bus Factor metric for repository sustainability.
This module defines BusFactorMetric, which inspects the number of unique recent
committers (from metadata) and estimates the project's resilience to developer
loss. It normalizes the committer count into [0,1] by dividing by 10 and capping
at 1.0: a repo with ≥10 active committers scores 1.0, while 0 committers scores
0.0. The metric also includes details showing the raw count.
"""

from __future__ import annotations
import time
from typing import Any, Dict
from datetime import datetime, timezone
from metric import Metric, MetricResult, clamp


class BusFactorMetric(Metric):
    """Assess knowledge distribution in the repo via recent committer count."""

    @property
    def name(self) -> str:
        return "bus_factor"

    def compute(self, metadata: dict[str, Any]) -> MetricResult:
        t0 = time.time()
        score = 0.0
        
        score += self._eval_organization(metadata["hf_metadata"]) * 0.6
        score += self._eval_contributors(metadata["repo_metadata"]) * 0.3
        score += self._eval_activity(metadata["hf_metadata"]) * 0.1
        
        return MetricResult(
            name=self.name,
            value=score,
            details={"success" :True},
            latency_ms=int((time.time() - t0) * 1000),
        )

    def _eval_contributors(self, model_info: Dict[str, Any]) -> float:
        """Evaluate based on number of contributors"""
        # This would ideally use git metadata, simplified for now
        num_contributors = model_info.get("unique_committers_count") or 0

        # Ensure num_contributors is an int
        try:
            num_contributors = int(num_contributors)
        except Exception:
            num_contributors = 0

        if num_contributors >= 10:
            return 1.0
        elif num_contributors >= 6:
            return 0.7
        elif num_contributors >= 3:
            return 0.5
        else:
            return 0.2  

    def _eval_organization(self, metadata: Dict[str, Any]) -> float:
        """Higher score for organizational backing"""
        author = metadata.get("author", "").lower()
        model_id = metadata.get("repo_id", "").lower()
        # Known organizations get higher scores
        organizations = [
            "google", "microsoft", "facebook", "meta", "openai", 
            "anthropic", "huggingface", "stanford", "mit", "berkeley",
            "research", "ai", "deepmind", "nvidia", "apple"
        ]
        
        # Check both author and model ID for organization indicators
        search_text = f"{author} {model_id}"
        for org in organizations:
            if org in search_text:
                return 1.0
        
        # Check if it looks like an organization (not individual name)
        if any(indicator in search_text for indicator in ["team", "lab", "corp", "inc", "ltd", "research", "ai", "institute"]):
            return 0.8
        
        return 0.3  # Individual author
    
    def _eval_activity(self, model_info: Dict[str, Any]) -> float:
        """Evaluate recent activity based on last modified date"""
        last_modified = model_info.get("lastModified")
        if not last_modified:
            return 0.2
        
        # Parse date and calculate days since last update
        try:
            last_date = datetime.fromisoformat(last_modified.replace('Z', '+00:00'))
            days_old = (datetime.now(timezone.utc) - last_date).days
            
            if days_old <= 30:
                return 1.0
            elif days_old <= 90:
                return 0.7
            elif days_old <= 365:
                return 0.4
            else:
                return 0.1
        except:
            return 0.2