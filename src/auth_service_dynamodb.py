"""
Updated Authentication Service for DynamoDB
"""

import bcrypt
import jwt
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
import logging

from dynamodb_service import DynamoDBService, UserRole

logger = logging.getLogger(__name__)


class AuthService:
    """
    Handles user authentication and JWT token management.
    (Updated to work with DynamoDB instead of PostgreSQL)
    """
    
    def __init__(self, db_service: DynamoDBService, secret_key: str, jwt_secret: Optional[str] = None):
        """
        Initialize auth service.
        
        Args:
            db_service: DynamoDB service instance
            secret_key: Secret key for password hashing
            jwt_secret: Secret key for JWT tokens (defaults to secret_key)
        """
        self.db_service = db_service
        self.secret_key = secret_key
        self.jwt_secret = jwt_secret or secret_key
        
        # password policy
        self.min_password_length = 8
        self.require_uppercase = True
        self.require_lowercase = True
        self.require_digit = True
        self.require_special = True
    
    def create_user(
        self,
        username: str,
        password: str,
        role: UserRole = UserRole.SEARCHER
    ) -> Dict[str, Any]:
        """
        Create a new user.
        
        Args:
            username: Unique username
            password: Plain text password (will be hashed)
            role: User role
            
        Returns:
            Created user data
            
        Raises:
            ValueError: If username exists or password is invalid
        """
        # validate username
        if not username or len(username) < 3:
            raise ValueError("Username must be at least 3 characters")
        
        if not re.match(r'^[a-zA-Z0-9_-]+$', username):
            raise ValueError("Username can only contain letters, numbers, hyphens, and underscores")
        
        # check if user exists
        existing = self.db_service.get_user(username)
        if existing:
            raise ValueError(f"User '{username}' already exists")
        
        # validate password
        self._validate_password(password)
        
        # hash password
        password_hash = bcrypt.hashpw(
            password.encode('utf-8'),
            bcrypt.gensalt(rounds=12)
        ).decode('utf-8')
        
        # create user in DynamoDB
        user_data = {
            'username': username,
            'password_hash': password_hash,
            'role': role.value if isinstance(role, UserRole) else role,
        }
        
        user = self.db_service.create_user(user_data)
        logger.info(f"Created user: {username} with role {role}")
        
        return user
    
    def authenticate(self, username: str, password: str) -> Dict[str, Any]:
        """
        Authenticate user and generate JWT token.
        
        Args:
            username: Username
            password: Plain text password
            
        Returns:
            Dictionary with token and user info
            
        Raises:
            ValueError: If authentication fails
        """
        # get user from DynamoDB
        user = self.db_service.get_user(username)
        
        if not user:
            logger.warning(f"Authentication failed: User '{username}' not found")
            raise ValueError("Invalid username or password")
        
        if not user.get('is_active', True):
            logger.warning(f"Authentication failed: User '{username}' is inactive")
            raise ValueError("Account is inactive")
        
        # verify password
        password_hash = user['password_hash'].encode('utf-8')
        password_bytes = password.encode('utf-8')
        
        if not bcrypt.checkpw(password_bytes, password_hash):
            logger.warning(f"Authentication failed: Invalid password for '{username}'")
            raise ValueError("Invalid username or password")
        
        # generate JWT token
        token = self._generate_token(user)
        
        # store token in DynamoDB for tracking
        token_data = {
            'token_id': token['token_id'],
            'username': username,
        }
        self.db_service.create_token(token_data)
        
        logger.info(f"User '{username}' authenticated successfully")
        
        return {
            'token': token['jwt'],
            'token_id': token['token_id'],
            'username': username,
            'role': user['role'],
            'expires_at': token['expires_at']
        }
    
    def validate_token(self, token: str) -> Dict[str, Any]:
        """
        Validate JWT token and return user info.
        
        Args:
            token: JWT token string
            
        Returns:
            Dictionary with user info
            
        Raises:
            ValueError: If token is invalid or expired
        """
        try:
            # decode JWT
            payload = jwt.decode(
                token,
                self.jwt_secret,
                algorithms=['HS256']
            )
            
            token_id = payload.get('token_id')
            username = payload.get('username')
            
            if not token_id or not username:
                raise ValueError("Invalid token payload")
            
            # check token in DynamoDB
            token_record = self.db_service.get_token(token_id)
            if not token_record:
                raise ValueError("Token not found or has been revoked")
            
            # check call count limit (1000 per token)
            if token_record.get('call_count', 0) >= 1000:
                raise ValueError("Token usage limit exceeded")
            
            # increment usage count
            self.db_service.increment_token_usage(token_id)
            
            # get user info
            user = self.db_service.get_user(username)
            if not user or not user.get('is_active', True):
                raise ValueError("User not found or inactive")
            
            return {
                'username': username,
                'role': user['role'],
                'token_id': token_id,
                'call_count': token_record.get('call_count', 0) + 1
            }
            
        except jwt.ExpiredSignatureError:
            logger.warning("Token expired")
            raise ValueError("Token has expired")
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            raise ValueError("Invalid token")
    
    def revoke_token(self, token_id: str) -> bool:
        """Revoke a token"""
        return self.db_service.delete_token(token_id)
    
    def get_user_tokens(self, username: str) -> list:
        """Get all active tokens for a user"""
        return self.db_service.get_user_tokens(username)
    
    def change_password(self, username: str, old_password: str, new_password: str) -> bool:
        """
        Change user password.
        
        Args:
            username: Username
            old_password: Current password
            new_password: New password
            
        Returns:
            True if successful
            
        Raises:
            ValueError: If old password is incorrect or new password is invalid
        """
        # authenticate with old password first
        user = self.db_service.get_user(username)
        if not user:
            raise ValueError("User not found")
        
        password_hash = user['password_hash'].encode('utf-8')
        if not bcrypt.checkpw(old_password.encode('utf-8'), password_hash):
            raise ValueError("Current password is incorrect")
        
        # validate new password
        self._validate_password(new_password)
        
        # hash new password
        new_hash = bcrypt.hashpw(
            new_password.encode('utf-8'),
            bcrypt.gensalt(rounds=12)
        ).decode('utf-8')
        
        # update in DynamoDB
        self.db_service.update_user(username, {'password_hash': new_hash})
        
        logger.info(f"Password changed for user: {username}")
        return True
    
    def update_user_role(self, username: str, new_role: UserRole) -> Dict[str, Any]:
        """
        Update user role (admin only).
        
        Args:
            username: Username
            new_role: New role
            
        Returns:
            Updated user data
        """
        role_value = new_role.value if isinstance(new_role, UserRole) else new_role
        updated_user = self.db_service.update_user(username, {'role': role_value})
        
        if not updated_user:
            raise ValueError(f"User '{username}' not found")
        
        logger.info(f"Updated role for {username} to {role_value}")
        return updated_user
    
    def deactivate_user(self, username: str) -> bool:
        """Deactivate a user account"""
        self.db_service.update_user(username, {'is_active': False})
        logger.info(f"Deactivated user: {username}")
        return True
    
    def activate_user(self, username: str) -> bool:
        """Activate a user account"""
        self.db_service.update_user(username, {'is_active': True})
        logger.info(f"Activated user: {username}")
        return True
    
    def delete_user(self, username: str) -> bool:
        """
        Delete a user account.
        
        Args:
            username: Username to delete
            
        Returns:
            True if successful
        """
        # revoke all user tokens first
        tokens = self.get_user_tokens(username)
        for token in tokens:
            self.revoke_token(token['token_id'])
        
        # delete user
        success = self.db_service.delete_user(username)
        
        if success:
            logger.info(f"Deleted user: {username}")
        
        return success
    
    def list_users(self) -> list:
        """List all users (admin only)"""
        users = self.db_service.list_users()
        
        # remove password hashes from response
        for user in users:
            user.pop('password_hash', None)
        
        return users
    
    def _validate_password(self, password: str):
        """
        Validate password against policy.
        
        Raises:
            ValueError: If password doesn't meet requirements
        """
        if len(password) < self.min_password_length:
            raise ValueError(f"Password must be at least {self.min_password_length} characters")
        
        if self.require_uppercase and not re.search(r'[A-Z]', password):
            raise ValueError("Password must contain at least one uppercase letter")
        
        if self.require_lowercase and not re.search(r'[a-z]', password):
            raise ValueError("Password must contain at least one lowercase letter")
        
        if self.require_digit and not re.search(r'\d', password):
            raise ValueError("Password must contain at least one digit")
        
        if self.require_special and not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            raise ValueError("Password must contain at least one special character")
    
    def _generate_token(self, user: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate JWT token for user.
        
        Args:
            user: User data
            
        Returns:
            Dictionary with token info
        """
        import uuid
        
        token_id = str(uuid.uuid4())
        
        # token expires in 10 hours
        expires_at = datetime.now(timezone.utc) + timedelta(hours=10)
        
        payload = {
            'token_id': token_id,
            'username': user['username'],
            'role': user['role'],
            'iat': datetime.now(timezone.utc),
            'exp': expires_at
        }
        
        jwt_token = jwt.encode(payload, self.jwt_secret, algorithm='HS256')
        
        return {
            'token_id': token_id,
            'jwt': jwt_token,
            'expires_at': expires_at.isoformat()
        }


# example usage
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    
    from dynamodb_service import DynamoDBService
    import os
    
    # initialize services
    db_service = DynamoDBService(
        aws_access_key=os.environ.get('AWS_ACCESS_KEY_ID'),
        aws_secret_key=os.environ.get('AWS_SECRET_ACCESS_KEY'),
        region_name=os.environ.get('AWS_REGION', 'us-east-2')
    )
    auth_service = AuthService(
        db_service=db_service,
        secret_key=os.environ.get('SECRET_KEY', 'dev-secret-key'),
        jwt_secret=os.environ.get('JWT_SECRET', 'dev-jwt-secret')
    )
    
    # create a test user
    try:
        user = auth_service.create_user(
            username='testuser',
            password='TestPass123!',
            role=UserRole.UPLOADER
        )
        print(f"Created user: {user}")
        
        # authenticate
        auth_result = auth_service.authenticate('testuser', 'TestPass123!')
        print(f"Authentication successful: {auth_result['token']}")
        
        # validate token
        validation = auth_service.validate_token(auth_result['token'])
        print(f"Token valid: {validation}")
        
    except ValueError as e:
        print(f"Error: {e}")