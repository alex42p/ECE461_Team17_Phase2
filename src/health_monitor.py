"""
Health monitoring service for tracking system component health.
"""

import time
import requests
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import os

@dataclass
class ComponentHealth:
    """Health status for a system component."""
    name: str
    status: str  # ok, degraded, critical, unknown
    response_time_ms: Optional[float] = None
    error_message: Optional[str] = None
    last_checked: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

class HealthMonitor:
    """Monitor health of system components."""
    
    def __init__(self):
        self.start_time = datetime.utcnow()
        self.request_counts = {
            "total": 0,
            "success": 0,
            "error": 0
        }
        self.route_stats = {}  # route -> {count, errors}
    
    def get_uptime_seconds(self) -> float:
        """Get system uptime in seconds."""
        return (datetime.utcnow() - self.start_time).total_seconds()
    
    def record_request(self, route: str, success: bool):
        """Record a request for statistics."""
        self.request_counts["total"] += 1
        if success:
            self.request_counts["success"] += 1
        else:
            self.request_counts["error"] += 1
        
        if route not in self.route_stats:
            self.route_stats[route] = {"count": 0, "errors": 0}
        
        self.route_stats[route]["count"] += 1
        if not success:
            self.route_stats[route]["errors"] += 1
    
    def check_database_health(self) -> ComponentHealth:
        """Check database connectivity and response time."""
        from database import get_db
        
        start_time = time.time()
        try:
            session = get_db()
            # Simple query to test connection
            session.execute("SELECT 1")
            session.close()
            
            response_time_ms = (time.time() - start_time) * 1000
            
            return ComponentHealth(
                name="database",
                status="ok",
                response_time_ms=round(response_time_ms, 2),
                last_checked=datetime.utcnow().isoformat()
            )
        except Exception as e:
            return ComponentHealth(
                name="database",
                status="critical",
                error_message=str(e),
                last_checked=datetime.utcnow().isoformat()
            )
    
    def check_s3_health(self) -> ComponentHealth:
        """Check S3 connectivity."""
        import boto3
        from botocore.exceptions import ClientError
        
        start_time = time.time()
        try:
            s3_client = boto3.client('s3')
            # List buckets to test connection
            s3_client.list_buckets()
            
            response_time_ms = (time.time() - start_time) * 1000
            
            return ComponentHealth(
                name="s3_storage",
                status="ok",
                response_time_ms=round(response_time_ms, 2),
                last_checked=datetime.utcnow().isoformat()
            )
        except ClientError as e:
            return ComponentHealth(
                name="s3_storage",
                status="critical",
                error_message=str(e),
                last_checked=datetime.utcnow().isoformat()
            )
        except Exception as e:
            # If S3 not configured, mark as unknown
            return ComponentHealth(
                name="s3_storage",
                status="unknown",
                error_message=f"S3 not configured: {str(e)}",
                last_checked=datetime.utcnow().isoformat()
            )
    
    def check_github_api_health(self) -> ComponentHealth:
        """Check GitHub API connectivity."""
        start_time = time.time()
        try:
            response = requests.get(
                "https://api.github.com/rate_limit",
                headers={"Authorization": f"token {os.environ.get('GITHUB_TOKEN', '')}"},
                timeout=5
            )
            
            response_time_ms = (time.time() - start_time) * 1000
            
            if response.status_code == 200:
                rate_limit = response.json()
                remaining = rate_limit.get("rate", {}).get("remaining", 0)
                
                status = "ok" if remaining > 100 else "degraded"
                
                return ComponentHealth(
                    name="github_api",
                    status=status,
                    response_time_ms=round(response_time_ms, 2),
                    last_checked=datetime.utcnow().isoformat(),
                    details={"rate_limit_remaining": remaining}
                )
            else:
                return ComponentHealth(
                    name="github_api",
                    status="degraded",
                    error_message=f"HTTP {response.status_code}",
                    last_checked=datetime.utcnow().isoformat()
                )
        except Exception as e:
            return ComponentHealth(
                name="github_api",
                status="critical",
                error_message=str(e),
                last_checked=datetime.utcnow().isoformat()
            )
    
    def check_huggingface_api_health(self) -> ComponentHealth:
        """Check HuggingFace API connectivity."""
        start_time = time.time()
        try:
            response = requests.get(
                "https://huggingface.co/api/models?limit=1",
                timeout=5
            )
            
            response_time_ms = (time.time() - start_time) * 1000
            
            if response.status_code == 200:
                return ComponentHealth(
                    name="huggingface_api",
                    status="ok",
                    response_time_ms=round(response_time_ms, 2),
                    last_checked=datetime.utcnow().isoformat()
                )
            else:
                return ComponentHealth(
                    name="huggingface_api",
                    status="degraded",
                    error_message=f"HTTP {response.status_code}",
                    last_checked=datetime.utcnow().isoformat()
                )
        except Exception as e:
            return ComponentHealth(
                name="huggingface_api",
                status="critical",
                error_message=str(e),
                last_checked=datetime.utcnow().isoformat()
            )
    
    def get_component_health(self) -> List[ComponentHealth]:
        """Get health status of all components."""
        return [
            self.check_database_health(),
            self.check_s3_health(),
            self.check_github_api_health(),
            self.check_huggingface_api_health()
        ]
    
    def get_overall_status(self) -> str:
        """
        Get overall system health status.
        
        Returns:
            "ok", "degraded", "critical", or "unknown"
        """
        components = self.get_component_health()
        
        if any(c.status == "critical" for c in components):
            return "critical"
        elif any(c.status == "degraded" for c in components):
            return "degraded"
        elif all(c.status == "ok" for c in components):
            return "ok"
        else:
            return "unknown"
    
    def get_health_summary(self) -> Dict[str, Any]:
        """Get complete health summary."""
        components = self.get_component_health()
        
        return {
            "status": self.get_overall_status(),
            "uptime_seconds": round(self.get_uptime_seconds(), 2),
            "uptime_human": self._format_uptime(),
            "request_stats": self.request_counts.copy(),
            "components": [
                {
                    "name": c.name,
                    "status": c.status,
                    "response_time_ms": c.response_time_ms,
                    "error_message": c.error_message,
                    "last_checked": c.last_checked,
                    "details": c.details
                }
                for c in components
            ],
            "timestamp": datetime.utcnow().isoformat()
        }
    
    def get_route_statistics(self) -> Dict[str, Any]:
        """Get per-route request statistics."""
        return {
            "total_requests": self.request_counts["total"],
            "success_rate": (
                self.request_counts["success"] / self.request_counts["total"]
                if self.request_counts["total"] > 0 else 0
            ),
            "routes": self.route_stats.copy()
        }
    
    def _format_uptime(self) -> str:
        """Format uptime in human-readable form."""
        seconds = self.get_uptime_seconds()
        
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        
        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        parts.append(f"{secs}s")
        
        return " ".join(parts)

# Global health monitor instance
health_monitor = HealthMonitor()





