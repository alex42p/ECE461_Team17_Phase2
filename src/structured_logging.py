"""
Structured logging configuration with CloudWatch integration.
Implements JSON-formatted logging for better observability.
"""

import os
import sys
import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional
import structlog
from logging.handlers import RotatingFileHandler

class CloudWatchHandler(logging.Handler):
    """
    Custom handler to send logs to AWS CloudWatch.
    Falls back to local logging if CloudWatch is unavailable.
    """
    
    def __init__(self, log_group: str, log_stream: str):
        super().__init__()
        self.log_group = log_group
        self.log_stream = log_stream
        self.cloudwatch_available = False
        
        try:
            import boto3
            self.client = boto3.client('logs')
            self._ensure_log_group()
            self._ensure_log_stream()
            self.cloudwatch_available = True
        except Exception as e:
            print(f"CloudWatch not available: {e}")
            self.client = None
    
    def _ensure_log_group(self):
        """Ensure log group exists."""
        if not self.client:
            return
        
        try:
            self.client.create_log_group(logGroupName=self.log_group)
            # Set retention to 30 days
            self.client.put_retention_policy(
                logGroupName=self.log_group,
                retentionInDays=30
            )
        except self.client.exceptions.ResourceAlreadyExistsException:
            pass
        except Exception as e:
            print(f"Error creating log group: {e}")
    
    def _ensure_log_stream(self):
        """Ensure log stream exists."""
        if not self.client:
            return
        
        try:
            self.client.create_log_stream(
                logGroupName=self.log_group,
                logStreamName=self.log_stream
            )
        except self.client.exceptions.ResourceAlreadyExistsException:
            pass
        except Exception as e:
            print(f"Error creating log stream: {e}")
    
    def emit(self, record):
        """Send log record to CloudWatch."""
        if not self.cloudwatch_available or not self.client:
            return
        
        try:
            log_event = {
                'logGroupName': self.log_group,
                'logStreamName': self.log_stream,
                'logEvents': [
                    {
                        'timestamp': int(record.created * 1000),
                        'message': self.format(record)
                    }
                ]
            }
            
            self.client.put_log_events(**log_event)
        except Exception as e:
            # Don't let logging errors break the application
            print(f"Error sending to CloudWatch: {e}")

class JSONFormatter(logging.Formatter):
    """Format log records as JSON."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON string."""
        log_data = {
            "timestamp": datetime.utcfromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        # Add extra fields
        if hasattr(record, 'user'):
            log_data["user"] = record.user
        if hasattr(record, 'endpoint'):
            log_data["endpoint"] = record.endpoint
        if hasattr(record, 'status_code'):
            log_data["status_code"] = record.status_code
        if hasattr(record, 'request_id'):
            log_data["request_id"] = record.request_id
        
        return json.dumps(log_data)

def configure_logging(
    log_level: str = "INFO",
    log_file: str = "app.log",
    enable_cloudwatch: bool = True,
    cloudwatch_group: str = "/aws/ece461/package-registry",
    cloudwatch_stream: Optional[str] = None
):
    """
    Configure structured logging for the application.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Local log file path
        enable_cloudwatch: Whether to enable CloudWatch logging
        cloudwatch_group: CloudWatch log group name
        cloudwatch_stream: CloudWatch log stream name (defaults to hostname)
    """
    # Get log level from environment or parameter
    level_str = os.environ.get("LOG_LEVEL", log_level).upper()
    level = getattr(logging, level_str, logging.INFO)
    
    # Create formatter
    json_formatter = JSONFormatter()
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Console handler (JSON format)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(json_formatter)
    root_logger.addHandler(console_handler)
    
    # File handler (JSON format with rotation)
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5
    )
    file_handler.setFormatter(json_formatter)
    root_logger.addHandler(file_handler)
    
    # CloudWatch handler (if enabled)
    if enable_cloudwatch:
        if cloudwatch_stream is None:
            import socket
            cloudwatch_stream = f"{socket.gethostname()}-{datetime.utcnow().strftime('%Y%m%d')}"
        
        cloudwatch_handler = CloudWatchHandler(cloudwatch_group, cloudwatch_stream)
        cloudwatch_handler.setFormatter(json_formatter)
        root_logger.addHandler(cloudwatch_handler)
    
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

class RequestLogger:
    """Helper class for logging HTTP requests."""
    
    @staticmethod
    def log_request(
        endpoint: str,
        method: str,
        user: Optional[str] = None,
        status_code: Optional[int] = None,
        response_time_ms: Optional[float] = None,
        error: Optional[str] = None
    ):
        """Log an HTTP request."""
        logger = logging.getLogger("api.requests")
        
        log_data = {
            "endpoint": endpoint,
            "method": method,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        if user:
            log_data["user"] = user
        if status_code:
            log_data["status_code"] = status_code
        if response_time_ms:
            log_data["response_time_ms"] = round(response_time_ms, 2)
        if error:
            log_data["error"] = error
        
        # Determine log level based on status code
        if status_code and status_code >= 500:
            logger.error(f"Request to {endpoint}", extra=log_data)
        elif status_code and status_code >= 400:
            logger.warning(f"Request to {endpoint}", extra=log_data)
        else:
            logger.info(f"Request to {endpoint}", extra=log_data)
    
    @staticmethod
    def log_error(
        endpoint: str,
        method: str,
        error: Exception,
        user: Optional[str] = None
    ):
        """Log an error during request handling."""
        logger = logging.getLogger("api.errors")
        
        logger.error(
            f"Error in {method} {endpoint}: {str(error)}",
            extra={
                "endpoint": endpoint,
                "method": method,
                "user": user,
                "error_type": type(error).__name__,
                "error_message": str(error)
            },
            exc_info=True
        )

class AuditLogger:
    """Helper class for audit logging."""
    
    @staticmethod
    def log_action(
        action: str,
        artifact_id: str,
        artifact_type: str,
        user: str,
        details: Optional[Dict[str, Any]] = None
    ):
        """Log an audit action."""
        logger = logging.getLogger("audit")
        
        log_data = {
            "action": action,
            "artifact_id": artifact_id,
            "artifact_type": artifact_type,
            "user": user,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        if details:
            log_data["details"] = details
        
        logger.info(f"Audit: {action} on {artifact_type}/{artifact_id}", extra=log_data)

class SecurityLogger:
    """Helper class for security event logging."""
    
    @staticmethod
    def log_authentication_success(username: str, ip_address: str):
        """Log successful authentication."""
        logger = logging.getLogger("security.auth")
        logger.info(
            f"Authentication successful: {username}",
            extra={
                "event": "auth_success",
                "username": username,
                "ip_address": ip_address,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
    
    @staticmethod
    def log_authentication_failure(username: str, ip_address: str, reason: str):
        """Log failed authentication attempt."""
        logger = logging.getLogger("security.auth")
        logger.warning(
            f"Authentication failed: {username}",
            extra={
                "event": "auth_failure",
                "username": username,
                "ip_address": ip_address,
                "reason": reason,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
    
    @staticmethod
    def log_authorization_failure(
        username: str,
        endpoint: str,
        required_role: Optional[str] = None
    ):
        """Log authorization failure."""
        logger = logging.getLogger("security.authz")
        logger.warning(
            f"Authorization failed: {username} -> {endpoint}",
            extra={
                "event": "authz_failure",
                "username": username,
                "endpoint": endpoint,
                "required_role": required_role,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
    
    @staticmethod
    def log_suspicious_activity(
        description: str,
        user: Optional[str] = None,
        ip_address: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """Log suspicious activity."""
        logger = logging.getLogger("security.suspicious")
        
        log_data = {
            "event": "suspicious_activity",
            "description": description,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        if user:
            log_data["user"] = user
        if ip_address:
            log_data["ip_address"] = ip_address
        if details:
            log_data["details"] = details
        
        logger.warning(f"Suspicious activity: {description}", extra=log_data)

# Initialize logging on module import
configure_logging(
    log_level=os.environ.get("LOG_LEVEL", "INFO"),
    log_file=os.environ.get("LOG_FILE", "app.log"),
    enable_cloudwatch=os.environ.get("ENABLE_CLOUDWATCH", "false").lower() == "true"
)

# Export logger instances
request_logger = RequestLogger()
audit_logger = AuditLogger()
security_logger = SecurityLogger()





