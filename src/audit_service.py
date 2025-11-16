"""
Audit trail service for tracking all operations on artifacts.
Implements comprehensive logging of CRUD operations and downloads.
"""

from datetime import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from database import AuditLog, AuditAction

class AuditService:
    """Service for managing audit trails."""
    
    def __init__(self, session: Session):
        self.session = session
    
    def log_action(
        self,
        artifact_id: str,
        artifact_type: str,
        action: AuditAction,
        username: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> AuditLog:
        """
        Log an action in the audit trail.
        
        Args:
            artifact_id: Artifact identifier
            artifact_type: Type of artifact (model, dataset, code)
            action: Action performed
            username: Username performing the action
            details: Additional details about the action
            
        Returns:
            Created audit log entry
        """
        audit_entry = AuditLog(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            action=action,
            username=username,
            timestamp=datetime.utcnow(),
            details=details or {}
        )
        
        self.session.add(audit_entry)
        self.session.flush()
        
        return audit_entry
    
    def log_create(
        self,
        artifact_id: str,
        artifact_type: str,
        username: Optional[str] = None,
        artifact_name: Optional[str] = None,
        artifact_version: Optional[str] = None
    ):
        """Log artifact creation."""
        return self.log_action(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            action=AuditAction.CREATE,
            username=username,
            details={
                "name": artifact_name,
                "version": artifact_version,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
    
    def log_update(
        self,
        artifact_id: str,
        artifact_type: str,
        username: Optional[str] = None,
        changes: Optional[Dict[str, Any]] = None
    ):
        """Log artifact update."""
        return self.log_action(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            action=AuditAction.UPDATE,
            username=username,
            details={
                "changes": changes,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
    
    def log_download(
        self,
        artifact_id: str,
        artifact_type: str,
        username: Optional[str] = None,
        download_size: Optional[int] = None
    ):
        """Log artifact download."""
        return self.log_action(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            action=AuditAction.DOWNLOAD,
            username=username,
            details={
                "download_size_bytes": download_size,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
    
    def log_rate(
        self,
        artifact_id: str,
        artifact_type: str,
        username: Optional[str] = None,
        scores: Optional[Dict[str, Any]] = None
    ):
        """Log artifact rating/scoring."""
        return self.log_action(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            action=AuditAction.RATE,
            username=username,
            details={
                "scores": scores,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
    
    def log_delete(
        self,
        artifact_id: str,
        artifact_type: str,
        username: Optional[str] = None
    ):
        """Log artifact deletion."""
        return self.log_action(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            action=AuditAction.DELETE,
            username=username,
            details={
                "timestamp": datetime.utcnow().isoformat()
            }
        )
    
    def log_audit(
        self,
        artifact_id: str,
        artifact_type: str,
        username: Optional[str] = None
    ):
        """Log audit trail access."""
        return self.log_action(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            action=AuditAction.AUDIT,
            username=username,
            details={
                "timestamp": datetime.utcnow().isoformat()
            }
        )
    
    def get_artifact_audit_trail(
        self,
        artifact_id: str,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Get audit trail for a specific artifact.
        
        Args:
            artifact_id: Artifact identifier
            limit: Maximum number of entries to return
            offset: Number of entries to skip
            
        Returns:
            List of audit log entries
        """
        logs = (
            self.session.query(AuditLog)
            .filter(AuditLog.artifact_id == artifact_id)
            .order_by(AuditLog.timestamp.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )
        
        return [log.to_dict() for log in logs]
    
    def get_user_audit_trail(
        self,
        username: str,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Get audit trail for a specific user.
        
        Args:
            username: Username
            limit: Maximum number of entries to return
            offset: Number of entries to skip
            
        Returns:
            List of audit log entries
        """
        logs = (
            self.session.query(AuditLog)
            .filter(AuditLog.username == username)
            .order_by(AuditLog.timestamp.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )
        
        return [log.to_dict() for log in logs]
    
    def get_download_history(
        self,
        artifact_id: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get download history for a specific artifact.
        
        Args:
            artifact_id: Artifact identifier
            limit: Maximum number of entries to return
            
        Returns:
            List of download audit entries
        """
        logs = (
            self.session.query(AuditLog)
            .filter(
                AuditLog.artifact_id == artifact_id,
                AuditLog.action == AuditAction.DOWNLOAD
            )
            .order_by(AuditLog.timestamp.desc())
            .limit(limit)
            .all()
        )
        
        return [log.to_dict() for log in logs]
    
    def get_action_count(
        self,
        artifact_id: str,
        action: Optional[AuditAction] = None
    ) -> int:
        """
        Get count of actions for an artifact.
        
        Args:
            artifact_id: Artifact identifier
            action: Optional specific action to count
            
        Returns:
            Count of matching audit entries
        """
        query = self.session.query(AuditLog).filter(
            AuditLog.artifact_id == artifact_id
        )
        
        if action:
            query = query.filter(AuditLog.action == action)
        
        return query.count()
    
    def get_recent_activity(
        self,
        limit: int = 50,
        action: Optional[AuditAction] = None
    ) -> List[Dict[str, Any]]:
        """
        Get recent system activity.
        
        Args:
            limit: Maximum number of entries to return
            action: Optional action filter
            
        Returns:
            List of recent audit entries
        """
        query = self.session.query(AuditLog)
        
        if action:
            query = query.filter(AuditLog.action == action)
        
        logs = (
            query
            .order_by(AuditLog.timestamp.desc())
            .limit(limit)
            .all()
        )
        
        return [log.to_dict() for log in logs]
    
    def get_audit_statistics(self) -> Dict[str, Any]:
        """
        Get overall audit statistics.
        
        Returns:
            Dictionary with audit statistics
        """
        from sqlalchemy import func
        
        # Count by action type
        action_counts = (
            self.session.query(
                AuditLog.action,
                func.count(AuditLog.id)
            )
            .group_by(AuditLog.action)
            .all()
        )
        
        # Count unique users
        unique_users = (
            self.session.query(func.count(func.distinct(AuditLog.username)))
            .scalar()
        )
        
        # Count unique artifacts
        unique_artifacts = (
            self.session.query(func.count(func.distinct(AuditLog.artifact_id)))
            .scalar()
        )
        
        return {
            "total_events": sum(count for _, count in action_counts),
            "action_breakdown": {
                action.value: count for action, count in action_counts
            },
            "unique_users": unique_users,
            "unique_artifacts": unique_artifacts,
            "timestamp": datetime.utcnow().isoformat()
        }




