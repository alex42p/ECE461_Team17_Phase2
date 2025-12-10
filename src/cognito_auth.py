"""
AWS Cognito Authentication Service
Simplified authentication using AWS Cognito User Pools
Replaces 450+ lines of custom auth code with ~200 lines
"""
# mypy: ignore-errors
# pyright: reportOptionalMemberAccess=false

import os
import logging
from pathlib import Path
import boto3
import hmac
import hashlib
import base64
import traceback
from typing import Optional, Dict, Any
from botocore.exceptions import ClientError

class CognitoAuthService:
    """Lightweight authentication service using AWS Cognito."""
    
    def __init__(self, aws_access_key: Optional[str] = None, aws_secret_key: Optional[str] = None):
        """Initialize Cognito client with environment variables."""
        # logger setup
        self.__name__ = self.__class__.__name__
        self.logger = logging.getLogger(self.__name__)
        self.logger.setLevel(logging.DEBUG)
        try:
            root_dir = Path(__file__).resolve().parents[1]
        except Exception:
            root_dir = Path('.')
        logs_dir = root_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_file = logs_dir / f"{self.__name__}.log"
        if not any(isinstance(h, logging.FileHandler) and h.baseFilename == str(log_file) for h in self.logger.handlers):
            fh = logging.FileHandler(str(log_file), mode='w')
            fh.setLevel(logging.DEBUG)
            fmt = logging.Formatter("%(asctime)s %(levelname)s: %(message)s")
            fh.setFormatter(fmt)
            self.logger.addHandler(fh)

        self.region = os.environ.get('AWS_REGION', 'us-east-2')
        self.user_pool_id = os.environ.get('AWS_COGNITO_USER_POOL_ID')
        self.client_id = os.environ.get('AWS_COGNITO_CLIENT_ID')
        self.client_secret = os.environ.get('AWS_COGNITO_CLIENT_SECRET')

        # Log initial config
        self.logger.debug(f"Cognito region={self.region}")
        self.logger.debug(f"Cognito user_pool_id set={bool(self.user_pool_id)}")
        self.logger.debug(f"Cognito client_id set={bool(self.client_id)}")

        # Enable Cognito client if required Cognito env vars are present. Prefer explicit AWS keys
        # when provided, otherwise rely on environment/instance role and boto3 defaults.
        # Falls back to legacy auth if Cognito not configured
        if self.user_pool_id and self.client_id:
            try:
                if aws_access_key and aws_secret_key:
                    self.client = boto3.client('cognito-idp',
                                                region_name=self.region,
                                                aws_access_key_id=aws_access_key,
                                                aws_secret_access_key=aws_secret_key,
                    )
                else:
                    self.client = boto3.client('cognito-idp', region_name=self.region)
                self.enabled = True
                self.logger.info("✅ Cognito client initialized and enabled")
            except Exception as e:
                self._log_exception("Failed to initialize boto3 Cognito client", e)
                self.client = None
                self.enabled = False
                self.logger.info("⚠️  Cognito client initialization failed - using legacy auth")
        else:
            self.logger.info("⚠️  Cognito env vars not set - using legacy authentication")
            self.client = None
            self.enabled = False
            # self.logger.debug("   To enable: Run ./scripts/setup_cognito.sh and set environment variables")
        
        self.logger.info("Initialized CognitoAuthService")

    # --- Logging helpers ---
    def _mask(self, s: Optional[str], keep: int = 6) -> str:
        """Return masked version of string (useful for IDs)."""
        if not s:
            return ''
        if len(s) <= keep:
            return '*' * len(s)
        return s[:keep] + '...' + '*' * (len(s) - keep - 3)

    def _log_exception(self, msg: str, exc: Exception) -> None:
        """Log exception with stack trace.

        Avoid logging secrets; include exception type and message and stack for diagnostics.
        """
        self.logger.error(f"%s: %s", msg, str(exc))
        # Log full stack trace at debug level to avoid noisy logs by default
        tb = traceback.format_exc()
        self.logger.debug("Stack trace:\n%s", tb)
    
    def _get_secret_hash(self, username: str) -> str:
        """Generate secret hash for Cognito authentication."""
        message = username + self.client_id if username and self.client_id else ''
        secret = self.client_secret.encode() if self.client_secret else b''
        dig = hmac.new(secret, msg=message.encode(), digestmod=hashlib.sha256).digest()
        secret_hash = base64.b64encode(dig).decode()
        # Do not log secret hash value itself — log its length for diagnostics
        self.logger.debug("Computed secret_hash length=%d for username=%s", len(secret_hash), username)
        return secret_hash
    
    def authenticate(self, username: str, password: str) -> Dict[str, Any]:
        """
        Authenticate user with Cognito. 
        
        Returns:
            {
                "access_token": str,
                "id_token": str,
                "refresh_token": str,
                "expires_in": int,
                "user": {
                    "username": str,
                    "email": str,
                    "role": str
                }
            }
        """
        if not self.enabled:
            self.logger.error("Attempt to authenticate but Cognito client not enabled")
            raise ValueError("Cognito is not configured properly. Authentication is disabled.")
        
        try:
            self.logger.info("Authenticating user: %s (password omitted)", username)
            response = self.client.admin_initiate_auth(
                UserPoolId=self.user_pool_id,
                ClientId=self.client_id,
                AuthFlow='ADMIN_USER_PASSWORD_AUTH',
                AuthParameters={
                    'USERNAME': username,
                    'PASSWORD': password,
                    'SECRET_HASH': self._get_secret_hash(username)
                }
            )

            # Avoid logging tokens. Log presence and non-sensitive metadata.
            auth_result = response.get('AuthenticationResult', {})
            expires_in = auth_result.get('ExpiresIn')
            self.logger.debug("Authentication result contains keys: %s", list(auth_result.keys()))
            self.logger.info("Authentication succeeded for user=%s expires_in=%s", username, expires_in)

            # Get user attributes
            access_token = auth_result.get('AccessToken')
            user_info = self.get_user_info(access_token) if access_token else {}

            return {
                'access_token': auth_result.get('AccessToken'),
                'id_token': auth_result.get('IdToken'),
                'refresh_token': auth_result.get('RefreshToken'),
                'expires_in': expires_in,
                'user': user_info
            }
        except ClientError as e:
            # Log the error with details but avoid printing raw AWS response bodies
            error_code = e.response.get('Error', {}).get('Code')
            error_msg = e.response.get('Error', {}).get('Message')
            self._log_exception(f"Cognito ClientError during authenticate: {error_code} - {error_msg}", e)
            if error_code == 'NotAuthorizedException':
                raise ValueError("Invalid username or password")
            elif error_code == 'UserNotFoundException':
                raise ValueError("User not found")
            elif error_code == 'UserNotConfirmedException':
                raise ValueError("User not confirmed")
            else:
                raise ValueError(f"Authentication failed: {error_msg}")
    
    def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """Get user information from access token."""
        try:
            self.logger.debug("Getting user info (access_token omitted)")
            if not self.client:
                self.logger.error("get_user_info called but Cognito client not available")
                raise ValueError("Cognito client not initialized")

            response = self.client.get_user(AccessToken=access_token)
            self.logger.debug("get_user response keys: %s", list(response.keys()))

            # Extract attributes
            attributes = {attr['Name']: attr['Value'] for attr in response.get('UserAttributes', [])}

            # Default role based on email (temporary until custom attributes are set up)
            email = attributes.get('email', '')
            default_role = 'admin' if 'admin' in email else 'searcher'

            user = {
                'username': response.get('Username'),
                'email': email,
                'role': attributes.get('custom:role', default_role),
                'email_verified': attributes.get('email_verified', 'false') == 'true'
            }
            self.logger.info("Retrieved user info for username=%s email=%s role=%s", user.get('username'), self._mask(user.get('email')), user.get('role'))
            return user
        except ClientError as e:
            self._log_exception("Failed to get user info", e)
            raise ValueError(f"Failed to get user info: {e.response.get('Error', {}).get('Message')}")
    
    def create_user(self, username: str, email: str, password: str, role: str = 'searcher') -> Dict[str, Any]:
        """Create a new user in Cognito (admin only)."""
        try:
            self.logger.info("Creating user username=%s email=%s (password omitted)", username, self._mask(email))
            # Create user (without custom:role for now - attribute not in schema)
            response = self.client.admin_create_user(
                UserPoolId=self.user_pool_id,
                Username=email,
                UserAttributes=[
                    {'Name': 'email', 'Value': email},
                    {'Name': 'email_verified', 'Value': 'true'}
                ],
                TemporaryPassword=password,
                MessageAction='SUPPRESS'
            )

            # Set permanent password
            self.client.admin_set_user_password(
                UserPoolId=self.user_pool_id,
                Username=email,
                Password=password,
                Permanent=True
            )

            # Role will be inferred from email (admin@ = admin, others = searcher)
            inferred_role = 'admin' if 'admin' in email else role
            self.logger.debug("Created user in Cognito: %s", response.get('User', {}).get('Username'))

            return {
                'username': email,
                'email': email,
                'role': inferred_role,
                'status': 'CONFIRMED'
            }
        except ClientError as e:
            self._log_exception("Failed to create user", e)
            raise ValueError(f"Failed to create user: {e.response.get('Error', {}).get('Message')}")
    
    def delete_user(self, username: str) -> bool:
        """Delete a user from Cognito (admin only)."""
        try:
            self.logger.info("Deleting user: %s", username)
            self.client.admin_delete_user(
                UserPoolId=self.user_pool_id,
                Username=username
            )
            self.logger.debug("Deleted user: %s", username)
            return True
        except ClientError as e:
            self._log_exception("Failed to delete user", e)
            raise ValueError(f"Failed to delete user: {e.response.get('Error', {}).get('Message')}")
    
    def list_users(self, limit: int = 60) -> list:
        """List all users in the user pool (admin only)."""
        try:
            response = self.client.list_users(
                UserPoolId=self.user_pool_id,
                Limit=limit
            )
            
            users = []
            for user in response['Users']:
                attributes = {attr['Name']: attr['Value'] for attr in user['Attributes']}
                email = attributes.get('email', '')
                default_role = 'admin' if 'admin' in email else 'searcher'
                
                users.append({
                    'username': user['Username'],
                    'email': email,
                    'role': attributes.get('custom:role', default_role),
                    'status': user['UserStatus'],
                    'created': user['UserCreateDate'].isoformat(),
                    'enabled': user['Enabled']
                })
            
            return users
        except ClientError as e:
            self._log_exception("Failed to list users", e)
            raise ValueError(f"Failed to list users: {e.response.get('Error', {}).get('Message')}")
    
    def verify_token(self, access_token: str) -> Optional[Dict[str, Any]]:
        """
        Verify a Cognito access token and return user info.
        This replaces complex JWT validation logic.
        """
        try:
            self.logger.debug("Verifying token (access_token omitted)")
            user = self.get_user_info(access_token)
            self.logger.info("Token verified for username=%s", user.get('username'))
            return user
        except:
            self.logger.exception("Token verification failed")
            return None

