"""
Redis caching layer for external API responses.
"""

import json
import redis
from typing import Optional, Any
from functools import wraps
import hashlib
# from entities import HFModel

class CacheManager:
    """
    Manages Redis caching for external API calls.
    
    Key structure:
        hf:model:{model_id} -> HuggingFace model metadata (TTL: 1 hour)
        hf:dataset:{dataset_id} -> HuggingFace dataset metadata (TTL: 1 hour)
        gh:repo:{owner}/{repo} -> GitHub repo metadata (TTL: 6 hours)
        gh:contributors:{owner}/{repo} -> Contributor data (TTL: 12 hours)
        metrics:{artifact_id} -> Computed metrics (TTL: 24 hours)
    """
    
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_client = redis.from_url(redis_url, decode_responses=True)
        
        # TTL values in seconds
        self.TTL = {
            "hf_model": 3600,        # 1 hour
            "hf_dataset": 3600,      # 1 hour
            "gh_repo": 21600,        # 6 hours
            "gh_contributors": 43200,# 12 hours
            "metrics": 86400,        # 24 hours
        }
    
    def cache_get(self, key_prefix: str, identifier: str) -> Optional[dict]:
        """Get cached value."""
        key = f"{key_prefix}:{identifier}"
        try:
            data = self.redis_client.get(key)
            return json.loads(data) if data else None
        except Exception:
            return None
    
    def cache_set(self, key_prefix: str, identifier: str, value: dict, ttl_key: str):
        """Set cached value with TTL."""
        key = f"{key_prefix}:{identifier}"
        try:
            self.redis_client.setex(
                key,
                self.TTL[ttl_key],
                json.dumps(value)
            )
        except Exception:
            pass  # Fail silently - cache is optional
    
    def cache_delete(self, key_prefix: str, identifier: str):
        """Delete cached value (e.g., when artifact is updated)."""
        key = f"{key_prefix}:{identifier}"
        try:
            self.redis_client.delete(key)
        except Exception:
            pass


# Decorator for caching function results
def cached(key_prefix: str, ttl_key: str):
    """
    Decorator to cache function results.
    
    Usage:
        @cached("hf:model", "hf_model")
        def fetch_repo_metadata(model):
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key from function arguments
            cache_key = _generate_cache_key(*args, **kwargs)
            
            # Try to get from cache
            cache_mgr = CacheManager()
            cached_value = cache_mgr.cache_get(key_prefix, cache_key)
            
            if cached_value is not None:
                return cached_value
            
            # Call function
            result = func(*args, **kwargs)
            
            # Store in cache
            if result:
                cache_mgr.cache_set(key_prefix, cache_key, result, ttl_key)
            
            return result
        
        return wrapper
    return decorator


def _generate_cache_key(*args, **kwargs) -> str:
    """Generate unique cache key from function arguments."""
    key_parts = [str(arg) for arg in args] + [f"{k}={v}" for k, v in sorted(kwargs.items())]
    key_str = "|".join(key_parts)
    return hashlib.md5(key_str.encode()).hexdigest()
