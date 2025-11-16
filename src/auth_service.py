"""
Authentication service for user management and JWT token generation.
Implements bcrypt password hashing and JWT token-based authentication.
"""

import os
import re
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import bcrypt
import jwt
from sqlalchemy.orm import Session
from database import User, UserRole, TokenUsage


class AuthService:
    """Service for handling user authentication and authorization."""
    
    # JWT Configuration
    JWT_SECRET = os.environ.get("JWT_SECRET", secrets.token_urlsafe(64))
    JWT_ALGORITHM = "HS256"
    JWT_EXPIRATION_HOURS = 10
    
    # Token usage limits
    MAX_API_CALLS_PER_TOKEN = 1000
    
    def __init__(self, session: Session):
        """
        Initialize authentication service.
        
        Args:
            session: SQLAlchemy database session
        """
        self.session = session
    
    # ============================================================================
    # PASSWORD MANAGEMENT
    # ============================================================================
    
    @staticmethod
    def _hash_password(password: str) -> str:
        """
        Hash a password using bcrypt with 12 rounds.
        
        Args:
            password: Plain text password
            
        Returns:
            Bcrypt hashed password (string)
        """
        salt = bcrypt.gensalt(rounds=12)
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed.decode('utf-8')
    
    @staticmethod
    def _verify_password(password: str, password_hash: str) -> bool:
        """
        Verify a password against its bcrypt hash.
        
        Args:
            password: Plain text password to verify
            password_hash: Bcrypt hash to compare against
            
        Returns:
            True if password matches, False otherwise
        """
        try:
            return bcrypt.checkpw(
                password.encode('utf-8'),
                password_hash.encode('utf-8')
            )
        except Exception:
            return False
    
    @staticmethod
    def _is_password_strong(password: str) -> bool:
        """
        Check if password meets strength requirements.
        
        Requirements:
        - At least 8 characters
        - Contains uppercase letter
        - Contains lowercase letter
        - Contains digit
        - Contains special character (!@#$%^&*)
        
        Args:
            password: Password to validate
            
        Returns:
            True if password meets requirements, False otherwise
        """
        if len(password) < 8:
            return False
        
        has_upper = bool(re.search(r'[A-Z]', password))
        has_lower = bool(re.search(r'[a-z]', password))
        has_digit = bool(re.search(r'\d', password))
        has_special = bool(re.search(r'[!@#$%^&*(),.?":{}|<>]', password))
        
        return has_upper and has_lower and has_digit and has_special
    
    # ============================================================================
    # USER MANAGEMENT
    # ============================================================================
    
    def create_user(
        self,
        username: str,
        password: str,
        role: UserRole = UserRole.SEARCHER
    ) -> User:
        """
        Create a new user with hashed password.
        
        Args:
            username: Unique username
            password: Plain text password (will be hashed)
            role: User role (default: SEARCHER)
            
        Returns:
            Created User object
            
        Raises:
            ValueError: If username exists or password is weak
        """
        # Check if username already exists
        existing_user = self.session.query(User).filter_by(username=username).first()
        if existing_user:
            raise ValueError(f"Username '{username}' already exists")
        
        # Validate password strength
        if not self._is_password_strong(password):
            raise ValueError(
                "Password must be at least 8 characters and contain: "
                "uppercase, lowercase, digit, and special character (!@#$%^&*)"
            )
        
        # Hash password
        password_hash = self._hash_password(password)
        
        # Create user
        user = User(
            username=username,
            password_hash=password_hash,
            role=role,
            created_at=datetime.utcnow(),
            is_active=True
        )
        
        self.session.add(user)
        self.session.flush()
        
        return user
    
    def get_user(self, username: str) -> Optional[User]:
        """
        Get user by username.
        
        Args:
            username: Username to look up
            
        Returns:
            User object or None if not found
        """
        return self.session.query(User).filter_by(username=username).first()
    
    def delete_user(self, username: str, requesting_user: User) -> bool:
        """
        Delete a user (soft delete by setting is_active=False).
        
        Rules:
        - Users can delete themselves
        - Admins can delete any user
        
        Args:
            username: Username to delete
            requesting_user: User making the request
            
        Returns:
            True if deleted, False if not permitted
        """
        user = self.get_user(username)
        if not user:
            return False
        
        # Check permissions
        if requesting_user.username == username or requesting_user.role == UserRole.ADMIN:
            user.is_active = False
            self.session.flush()
            return True
        
        return False
    
    def list_users(self) -> list[Dict[str, Any]]:
        """
        List all users (admin only - caller should check permissions).
        
        Returns:
            List of user dictionaries
        """
        users = self.session.query(User).filter_by(is_active=True).all()
        return [user.to_dict() for user in users]
    
    # ============================================================================
    # JWT TOKEN MANAGEMENT
    # ============================================================================
    
    def generate_token(self, user: User) -> Dict[str, Any]:
        """
        Generate JWT token for authenticated user.
        
        Args:
            user: User object
            
        Returns:
            Dictionary with token, expiration, and user info
        """
        # Generate unique token ID
        token_id = secrets.token_urlsafe(32)
        
        # Calculate expiration
        expires_at = datetime.utcnow() + timedelta(hours=self.JWT_EXPIRATION_HOURS)
        
        # Create JWT payload
        payload = {
            "username": user.username,
            "role": user.role.value,
            "token_id": token_id,
            "exp": expires_at,
            "iat": datetime.utcnow()
        }
        
        # Sign token
        token = jwt.encode(payload, self.JWT_SECRET, algorithm=self.JWT_ALGORITHM)
        
        # Track token usage
        token_usage = TokenUsage(
            token_id=token_id,
            username=user.username,
            call_count=0,
            created_at=datetime.utcnow(),
            last_used_at=datetime.utcnow()
        )
        self.session.add(token_usage)
        self.session.flush()
        
        return {
            "token": token,
            "expires_at": expires_at.isoformat(),
            "username": user.username,
            "role": user.role.value,
            "token_id": token_id
        }
    
    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Verify and decode JWT token.
        
        Args:
            token: JWT token string
            
        Returns:
            Decoded payload if valid, None if invalid/expired
        """
        try:
            # Decode and verify signature
            payload = jwt.decode(
                token,
                self.JWT_SECRET,
                algorithms=[self.JWT_ALGORITHM]
            )
            
            # Check token usage limit
            token_id = payload.get("token_id")
            if token_id:
                token_usage = self.session.query(TokenUsage).filter_by(
                    token_id=token_id
                ).first()
                
                if token_usage:
                    # Check if exceeded max calls
                    if token_usage.call_count >= self.MAX_API_CALLS_PER_TOKEN:
                        return None
                    
                    # Increment usage
                    token_usage.call_count += 1
                    token_usage.last_used_at = datetime.utcnow()
                    self.session.flush()
            
            return payload
            
        except jwt.ExpiredSignatureError:
            # Token has expired
            return None
        except jwt.InvalidTokenError:
            # Invalid token (bad signature, malformed, etc.)
            return None
        except Exception:
            # Any other error
            return None
    
    # ============================================================================
    # AUTHENTICATION
    # ============================================================================
    
    def authenticate(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """
        Authenticate user with username and password.
        
        Args:
            username: Username
            password: Plain text password
            
        Returns:
            Dictionary with token and user info if successful, None if failed
        """
        # Get user
        user = self.get_user(username)
        if not user:
            return None
        
        # Check if account is active
        if not user.is_active:
            return None
        
        # Verify password
        if not self._verify_password(password, user.password_hash):
            return None
        
        # Generate and return token
        return self.generate_token(user)
    
    # ============================================================================
    # TOKEN USAGE TRACKING
    # ============================================================================
    
    def get_token_usage(self, token_id: str) -> Optional[Dict[str, Any]]:
        """
        Get usage statistics for a token.
        
        Args:
            token_id: Token ID
            
        Returns:
            Dictionary with usage stats or None if not found
        """
        token_usage = self.session.query(TokenUsage).filter_by(
            token_id=token_id
        ).first()
        
        if not token_usage:
            return None
        
        return {
            "token_id": token_usage.token_id,
            "username": token_usage.username,
            "call_count": token_usage.call_count,
            "max_calls": self.MAX_API_CALLS_PER_TOKEN,
            "remaining_calls": self.MAX_API_CALLS_PER_TOKEN - token_usage.call_count,
            "created_at": token_usage.created_at.isoformat(),
            "last_used_at": token_usage.last_used_at.isoformat()
        }
    
    def get_user_tokens(self, username: str) -> list[Dict[str, Any]]:
        """
        Get all active tokens for a user.
        
        Args:
            username: Username
            
        Returns:
            List of token usage dictionaries
        """
        tokens = self.session.query(TokenUsage).filter_by(username=username).all()
        return [
            {
                "token_id": t.token_id,
                "call_count": t.call_count,
                "created_at": t.created_at.isoformat(),
                "last_used_at": t.last_used_at.isoformat()
            }
            for t in tokens
        ]


# Module-level initialization check
if not os.environ.get("JWT_SECRET"):
    import warnings
    warnings.warn(
        "JWT_SECRET environment variable not set! Using random secret. "
        "This is INSECURE for production. Set JWT_SECRET in your environment.",
        UserWarning
    )


if __name__ == "__main__":
    # Test the authentication service
    from database import get_db, init_db
    
    print("Testing AuthService...")
    
    # Initialize database
    init_db()
    session = get_db()
    
    try:
        auth = AuthService(session)
        
        # Test password strength validation
        print("\n1. Testing password strength...")
        print(f"  'weak' is strong: {auth._is_password_strong('weak')}")  # False
        print(f"  'StrongPass123!' is strong: {auth._is_password_strong('StrongPass123!')}")  # True
        
        # Test user creation
        print("\n2. Creating test user...")
        user = auth.create_user("testuser", "SecurePass123!", UserRole.UPLOADER)
        print(f"  Created user: {user.username} with role {user.role.value}")
        
        # Test authentication
        print("\n3. Testing authentication...")
        result = auth.authenticate("testuser", "SecurePass123!")
        print(f"  Auth successful: {result is not None}")
        if result:
            print(f"  Token: {result['token'][:50]}...")
            print(f"  Expires: {result['expires_at']}")
        
        # Test wrong password
        print("\n4. Testing wrong password...")
        result = auth.authenticate("testuser", "WrongPassword")
        print(f"  Auth with wrong password: {result is not None}")  # Should be False
        
        # Test token verification
        print("\n5. Testing token verification...")
        result = auth.authenticate("testuser", "SecurePass123!")
        if result:
            payload = auth.verify_token(result['token'])
            print(f"  Token valid: {payload is not None}")
            print(f"  Username from token: {payload.get('username')}")
        
        session.commit()
        print("\nAll tests passed!")
        
    except Exception as e:
        session.rollback()
        print(f"\nError: {e}")
    finally:
        session.close()

