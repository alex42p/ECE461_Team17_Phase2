"""
Authorization middleware for Flask application.
Validates JWT tokens and enforces role-based access control.
"""

from functools import wraps
from typing import Callable, List, Optional
from flask import request, jsonify, g
from sqlalchemy.orm import Session
from database import UserRole, get_db, User
from auth_service import AuthService

class AuthorizationError(Exception):
    """Custom exception for authorization errors."""
    pass

def get_auth_service() -> AuthService:
    """Get AuthService instance with database session."""
    if not hasattr(g, 'db_session'):
        g.db_session = get_db()
    if not hasattr(g, 'auth_service'):
        g.auth_service = AuthService(g.db_session)
    return g.auth_service

def extract_token() -> Optional[str]:
    """
    Extract JWT token from X-Authorization header.
    
    Returns:
        Token string or None if not found
    """
    auth_header = request.headers.get('X-Authorization')
    if not auth_header:
        return None
    
    # Support both "Bearer <token>" and just "<token>" formats
    if auth_header.startswith('Bearer '):
        return auth_header[7:]  # Remove "Bearer " prefix
    
    return auth_header

def require_auth(required_roles: Optional[List[UserRole]] = None):
    """
    Decorator to require authentication and optionally check roles.
    
    Args:
        required_roles: List of roles allowed to access the endpoint.
                       If None, any authenticated user can access.
    
    Usage:
        @app.route('/admin/users')
        @require_auth([UserRole.ADMIN])
        def admin_users():
            # Only admins can access
            pass
        
        @app.route('/packages')
        @require_auth()
        def list_packages():
            # Any authenticated user can access
            pass
    """
    def decorator(f: Callable):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Extract token
            token = extract_token()
            if not token:
                return jsonify({
                    "error": "Authentication required",
                    "message": "X-Authorization header is required"
                }), 401
            
            # Verify token
            auth_service = get_auth_service()
            payload = auth_service.verify_token(token)
            
            if not payload:
                return jsonify({
                    "error": "Invalid or expired token",
                    "message": "Please authenticate again"
                }), 401
            
            # Store user info in request context
            g.current_user = {
                "username": payload["username"],
                "role": payload["role"],
                "token_id": payload["token_id"]
            }
            
            # Check role permissions if required
            if required_roles:
                user_role = UserRole(payload["role"])
                if user_role not in required_roles:
                    return jsonify({
                        "error": "Insufficient permissions",
                        "message": f"This endpoint requires one of: {[r.value for r in required_roles]}"
                    }), 403
            
            return f(*args, **kwargs)
        
        return decorated_function
    return decorator

def optional_auth():
    """
    Decorator to extract user info if token is provided, but don't require it.
    
    Usage:
        @app.route('/packages/search')
        @optional_auth()
        def search_packages():
            # Works for both authenticated and anonymous users
            user = g.get('current_user')
            if user:
                # Authenticated user
                pass
            else:
                # Anonymous user
                pass
    """
    def decorator(f: Callable):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            token = extract_token()
            
            if token:
                auth_service = get_auth_service()
                payload = auth_service.verify_token(token)
                
                if payload:
                    g.current_user = {
                        "username": payload["username"],
                        "role": payload["role"],
                        "token_id": payload["token_id"]
                    }
            
            return f(*args, **kwargs)
        
        return decorated_function
    return decorator

def check_permission(action: str, resource_owner: Optional[str] = None) -> bool:
    """
    Check if current user has permission to perform an action.
    
    Args:
        action: Action to perform (e.g., "upload", "download", "delete")
        resource_owner: Optional username of resource owner
        
    Returns:
        True if permitted, False otherwise
        
    Rules:
        - ADMIN can do anything
        - UPLOADER can upload and update their own artifacts
        - DOWNLOADER can download artifacts
        - SEARCHER can only search and view metadata
    """
    if not hasattr(g, 'current_user'):
        return False
    
    user = g.current_user
    role = UserRole(user["role"])
    username = user["username"]
    
    # Admin can do anything
    if role == UserRole.ADMIN:
        return True
    
    # Check specific permissions
    if action == "upload":
        return role in [UserRole.UPLOADER, UserRole.ADMIN]
    
    elif action == "download":
        return role in [UserRole.DOWNLOADER, UserRole.ADMIN]
    
    elif action == "search" or action == "view":
        return True  # All authenticated users can search/view
    
    elif action == "update" or action == "delete":
        # Users can update/delete their own resources, admins can do anything
        if role == UserRole.ADMIN:
            return True
        if role == UserRole.UPLOADER and resource_owner == username:
            return True
        return False
    
    return False

def get_current_user() -> Optional[dict]:
    """
    Get current authenticated user from request context.
    
    Returns:
        User dictionary or None if not authenticated
    """
    return g.get('current_user')

def require_admin():
    """Decorator that requires ADMIN role."""
    return require_auth([UserRole.ADMIN])

def require_uploader():
    """Decorator that requires UPLOADER or ADMIN role."""
    return require_auth([UserRole.UPLOADER, UserRole.ADMIN])

def require_downloader():
    """Decorator that requires DOWNLOADER or ADMIN role."""
    return require_auth([UserRole.DOWNLOADER, UserRole.ADMIN])

# Rate limiting support
class RateLimiter:
    """
    Simple in-memory rate limiter for API endpoints.
    For production, consider using Redis-based rate limiting.
    """
    
    def __init__(self):
        self.requests = {}  # username -> [(timestamp, endpoint)]
    
    def check_rate_limit(
        self,
        username: str,
        endpoint: str,
        max_requests: int = 100,
        window_seconds: int = 60
    ) -> bool:
        """
        Check if user is within rate limit.
        
        Args:
            username: Username
            endpoint: Endpoint being accessed
            max_requests: Maximum requests allowed in window
            window_seconds: Time window in seconds
            
        Returns:
            True if within limit, False if exceeded
        """
        from datetime import datetime, timedelta
        
        now = datetime.utcnow()
        cutoff = now - timedelta(seconds=window_seconds)
        
        # Get user's request history
        if username not in self.requests:
            self.requests[username] = []
        
        # Remove old requests outside window
        self.requests[username] = [
            (ts, ep) for ts, ep in self.requests[username]
            if ts > cutoff
        ]
        
        # Check if limit exceeded
        if len(self.requests[username]) >= max_requests:
            return False
        
        # Add current request
        self.requests[username].append((now, endpoint))
        return True

# Global rate limiter instance
rate_limiter = RateLimiter()

def rate_limit(max_requests: int = 100, window_seconds: int = 60):
    """
    Decorator to apply rate limiting to endpoints.
    
    Args:
        max_requests: Maximum requests per window
        window_seconds: Time window in seconds
    """
    def decorator(f: Callable):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = get_current_user()
            if not user:
                # Rate limit by IP for unauthenticated requests
                username = request.remote_addr or "anonymous"
            else:
                username = user["username"]
            
            endpoint = request.endpoint or request.path
            
            if not rate_limiter.check_rate_limit(username, endpoint, max_requests, window_seconds):
                return jsonify({
                    "error": "Rate limit exceeded",
                    "message": f"Maximum {max_requests} requests per {window_seconds} seconds"
                }), 429
            
            return f(*args, **kwargs)
        
        return decorated_function
    return decorator




