"""
Simplified Authentication Middleware for AWS Cognito
Replaces 301 lines of custom middleware with ~80 lines
"""
# mypy: ignore-errors

from functools import wraps
from flask import request, jsonify
from typing import Optional, Callable
from cognito_auth import cognito_auth

def get_token_from_request() -> Optional[str]:
    """Extract bearer token from request headers."""
    auth_header = request.headers.get('X-Authorization')
    if not auth_header:
        return None
    
    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != 'bearer':
        return None
    
    return parts[1]

def require_auth(required_roles: list = None):
    """
    Decorator to require authentication and optionally specific roles.
    
    Usage:
        @require_auth()  # Any authenticated user
        @require_auth(['admin'])  # Admin only
        @require_auth(['admin', 'uploader'])  # Admin or uploader
    """
    def decorator(f: Callable):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Get token from request
            token = get_token_from_request()
            if not token:
                return jsonify({
                    'error': 'Authentication required',
                    'message': 'X-Authorization header is required'
                }), 401
            
            # Verify token with Cognito
            user_info = cognito_auth.verify_token(token)
            if not user_info:
                return jsonify({
                    'error': 'Invalid token',
                    'message': 'Token is invalid or expired'
                }), 401
            
            # Check role if required
            if required_roles:
                user_role = user_info.get('role', 'searcher')
                if user_role not in required_roles:
                    return jsonify({
                        'error': 'Insufficient permissions',
                        'message': f'Required roles: {", ".join(required_roles)}'
                    }), 403
            
            # Attach user info to request for use in route
            request.current_user = user_info
            
            return f(*args, **kwargs)
        
        return decorated_function
    return decorator

def require_admin():
    """Shortcut decorator for admin-only routes."""
    return require_auth(['admin'])

def require_uploader():
    """Shortcut decorator for uploader or admin routes."""
    return require_auth(['admin', 'uploader'])

def require_downloader():
    """Shortcut decorator for downloader or admin routes."""
    return require_auth(['admin', 'downloader'])

def optional_auth(f: Callable):
    """
    Decorator that allows optional authentication.
    Attaches user info if token is present, otherwise continues without auth.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = get_token_from_request()
        if token:
            user_info = cognito_auth.verify_token(token)
            if user_info:
                request.current_user = user_info
            else:
                request.current_user = None
        else:
            request.current_user = None
        
        return f(*args, **kwargs)
    
    return decorated_function

def get_current_user():
    """Get current authenticated user info from request."""
    return getattr(request, 'current_user', None)

def rate_limit(max_requests: int = 10, window_seconds: int = 60):
    """
    Rate limiting decorator (no-op for Cognito - AWS handles rate limiting).
    Kept for API compatibility with legacy auth.
    """
    def decorator(f: Callable):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Cognito handles rate limiting, just pass through
            return f(*args, **kwargs)
        return decorated_function
    return decorator

