"""
AWS Cognito Authentication Service
Simplified authentication using AWS Cognito User Pools
Replaces 450+ lines of custom auth code with ~200 lines
"""
# mypy: ignore-errors
# pyright: reportOptionalMemberAccess=false

import os
import boto3
import hmac
import hashlib
import base64
from typing import Optional, Dict, Any
from botocore.exceptions import ClientError

class CognitoAuthService:
    """Lightweight authentication service using AWS Cognito."""
    
    def __init__(self):
        """Initialize Cognito client with environment variables."""
        self.region = os.environ.get('AWS_REGION', 'us-east-2')
        self.user_pool_id = os.environ.get('AWS_COGNITO_USER_POOL_ID')
        self.client_id = os.environ.get('AWS_COGNITO_CLIENT_ID')
        self.client_secret = os.environ.get('AWS_COGNITO_CLIENT_SECRET')
        
        # Make Cognito optional - only initialize if credentials are present
        if all([self.user_pool_id, self.client_id, self.client_secret]):
            self.client = boto3.client('cognito-idp', region_name=self.region)
            self.enabled = True
        else:
            self.client = None
            self.enabled = False
            print("⚠️  Cognito not configured - AWS Cognito features disabled")
            print("   To enable: Run ./scripts/setup_cognito.sh and set environment variables")
    
    def _get_secret_hash(self, username: str) -> str:
        """Generate secret hash for Cognito authentication."""
        message = username + self.client_id if username and self.client_id else ''
        secret = self.client_secret.encode() if self.client_secret else b''
        dig = hmac.new(secret, msg=message.encode(), digestmod=hashlib.sha256).digest()
        return base64.b64encode(dig).decode()
    
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
            raise ValueError("Cognito is not configured. Use legacy auth system.")
        
        try:
            response = self.client.admin_initiate_auth( # type: ignore
                UserPoolId=self.user_pool_id,
                ClientId=self.client_id,
                AuthFlow='ADMIN_USER_PASSWORD_AUTH',
                AuthParameters={
                    'USERNAME': username,
                    'PASSWORD': password,
                    'SECRET_HASH': self._get_secret_hash(username)
                }
            )
            
            # Get user attributes
            user_info = self.get_user_info(response['AuthenticationResult']['AccessToken'])
            
            return {
                'access_token': response['AuthenticationResult']['AccessToken'],
                'id_token': response['AuthenticationResult']['IdToken'],
                'refresh_token': response['AuthenticationResult']['RefreshToken'],
                'expires_in': response['AuthenticationResult']['ExpiresIn'],
                'user': user_info
            }
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NotAuthorizedException':
                raise ValueError("Invalid username or password")
            elif error_code == 'UserNotFoundException':
                raise ValueError("User not found")
            elif error_code == 'UserNotConfirmedException':
                raise ValueError("User not confirmed")
            else:
                raise ValueError(f"Authentication failed: {e.response['Error']['Message']}")
    
    def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """Get user information from access token."""
        try:
            if self.client:
                response = self.client.get_user(AccessToken=access_token)
            
            # Extract attributes
            attributes = {attr['Name']: attr['Value'] for attr in response['UserAttributes']}
            
            # Default role based on email (temporary until custom attributes are set up)
            email = attributes.get('email', '')
            default_role = 'admin' if 'admin' in email else 'searcher'
            
            return {
                'username': response['Username'],
                'email': email,
                'role': attributes.get('custom:role', default_role),
                'email_verified': attributes.get('email_verified', 'false') == 'true'
            }
        except ClientError as e:
            raise ValueError(f"Failed to get user info: {e.response['Error']['Message']}")
    
    def create_user(self, username: str, email: str, password: str, role: str = 'searcher') -> Dict[str, Any]:
        """Create a new user in Cognito (admin only)."""
        try:
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
            
            return {
                'username': email,
                'email': email,
                'role': inferred_role,
                'status': 'CONFIRMED'
            }
        except ClientError as e:
            raise ValueError(f"Failed to create user: {e.response['Error']['Message']}")
    
    def delete_user(self, username: str) -> bool:
        """Delete a user from Cognito (admin only)."""
        try:
            self.client.admin_delete_user(
                UserPoolId=self.user_pool_id,
                Username=username
            )
            return True
        except ClientError as e:
            raise ValueError(f"Failed to delete user: {e.response['Error']['Message']}")
    
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
            raise ValueError(f"Failed to list users: {e.response['Error']['Message']}")
    
    def verify_token(self, access_token: str) -> Optional[Dict[str, Any]]:
        """
        Verify a Cognito access token and return user info.
        This replaces complex JWT validation logic.
        """
        try:
            return self.get_user_info(access_token)
        except:
            return None

