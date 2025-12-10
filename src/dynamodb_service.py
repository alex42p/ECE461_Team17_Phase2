"""
DynamoDB Service for Package Registry
"""
# mypy: ignore-errors
# pyright: reportAttributeAccessIssue=false

import boto3
import os
import logging
from pathlib import Path
from typing import Optional, Dict, List, Any
from datetime import datetime, timezone
from decimal import Decimal
import json
from botocore.exceptions import ClientError
from enum import Enum

class UserRole(str, Enum):
    """User roles for authorization"""
    ADMIN = "admin"
    UPLOADER = "uploader"
    SEARCHER = "searcher"
    DOWNLOADER = "downloader"


class AuditAction(str, Enum):
    """Audit action types"""
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DOWNLOAD = "DOWNLOAD"
    RATE = "RATE"
    AUDIT = "AUDIT"
    DELETE = "DELETE"


class DynamoDBService:
    """
    Manages all DynamoDB operations for the package registry.
    
    Tables:
    - PackageRegistry: Main table for artifacts/packages
    - UserRegistry: User authentication and authorization
    - AuditLog: Comprehensive audit trail
    - TokenUsage: JWT token tracking
    """

    def __init__(self, aws_access_key: Optional[str], aws_secret_key: Optional[str], region_name: Optional[str] = None, endpoint_url: Optional[str] = None):
        """
        Initialize DynamoDB service.
        
        Args:
            region_name: AWS region
            endpoint_url: Optional endpoint for local development (DynamoDB Local)
        """
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

        self.region_name = region_name
        self.aws_access_key = aws_access_key
        self.aws_secret_key = aws_secret_key
        self.endpoint_url = endpoint_url

        if not all([self.region_name, self.aws_access_key, self.aws_secret_key]):
            self.logger.error("AWS credentials or region not properly set in environment variables.")
            raise ValueError("AWS credentials or region not properly set in environment variables.")

        # for local development, use DynamoDB Local
        if self.endpoint_url:
            self.dynamodb = boto3.resource(
                'dynamodb',
                region_name=self.region_name,
                endpoint_url=endpoint_url,
                aws_access_key_id=self.aws_access_key,
                aws_secret_access_key=self.aws_secret_key
            )
            self.logger.info(f"Connected to DynamoDB Local at {endpoint_url}")
        else:
            self.dynamodb = boto3.resource(
                'dynamodb',
                region_name=self.region_name,
                aws_access_key_id=self.aws_access_key,
                aws_secret_access_key=self.aws_secret_key
            )
            self.logger.info(f"Connected to DynamoDB in region {self.region_name}")
        
        self.table_prefix = os.environ.get('DYNAMODB_TABLE_PREFIX', 'ECE461-Team17')
        
        # initialize tables
        self.packages_table = None
        self.users_table = None
        self.audit_table = None
        self.tokens_table = None
        
        self._initialize_tables()
    
    def _initialize_tables(self):
        """Initialize DynamoDB table references"""
        try:
            self.packages_table = self.dynamodb.Table(f'{self.table_prefix}-Packages') 
            self.users_table = self.dynamodb.Table(f'{self.table_prefix}-Users')
            self.audit_table = self.dynamodb.Table(f'{self.table_prefix}-AuditLog')
            self.tokens_table = self.dynamodb.Table(f'{self.table_prefix}-Tokens')
            self.logger.info("DynamoDB tables initialized successfully")
        except Exception as e:
            self.logger.error(f"Error initializing tables: {e}")
            raise
    
    def create_tables(self):
        """
        Create all required DynamoDB tables with proper indexes.
        This should be run once during initial setup.
        """
        try:
            # packages table
            self._create_packages_table()
            
            # users table
            self._create_users_table()
            
            # audit log table
            self._create_audit_table()
            
            # token usage table
            self._create_tokens_table()
            
            self.logger.info("All DynamoDB tables created successfully")
            
        except Exception as e:
            self.logger.error(f"Error creating tables: {e}")
            raise
    
    def _create_packages_table(self):
        """Create Packages table for artifacts"""
        table_name = f'{self.table_prefix}-Packages'
        
        try:
            table = self.dynamodb.create_table(
                TableName=table_name,
                KeySchema=[
                    {'AttributeName': 'id', 'KeyType': 'HASH'},  # partition key
                ],
                AttributeDefinitions=[
                    {'AttributeName': 'id', 'AttributeType': 'S'},
                    {'AttributeName': 'name', 'AttributeType': 'S'},
                    {'AttributeName': 'artifact_type', 'AttributeType': 'S'},
                    {'AttributeName': 'created_at', 'AttributeType': 'S'},
                ],
                GlobalSecondaryIndexes=[
                    {
                        'IndexName': 'NameIndex',
                        'KeySchema': [
                            {'AttributeName': 'name', 'KeyType': 'HASH'},
                            {'AttributeName': 'created_at', 'KeyType': 'RANGE'},
                        ],
                        'Projection': {'ProjectionType': 'ALL'},
                        'ProvisionedThroughput': {
                            'ReadCapacityUnits': 5,
                            'WriteCapacityUnits': 5
                        }
                    },
                    {
                        'IndexName': 'TypeIndex',
                        'KeySchema': [
                            {'AttributeName': 'artifact_type', 'KeyType': 'HASH'},
                            {'AttributeName': 'created_at', 'KeyType': 'RANGE'},
                        ],
                        'Projection': {'ProjectionType': 'ALL'},
                        'ProvisionedThroughput': {
                            'ReadCapacityUnits': 5,
                            'WriteCapacityUnits': 5
                        }
                    },
                ],
                BillingMode='PAY_PER_REQUEST',  # on demand pricing
            )
            
            table.wait_until_exists()
            self.logger.info(f"Created table: {table_name}")
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceInUseException':
                self.logger.info(f"Table {table_name} already exists")
            else:
                raise
    
    def _create_users_table(self):
        """Create Users table for authentication"""
        table_name = f'{self.table_prefix}-Users'
        
        try:
            table = self.dynamodb.create_table(
                TableName=table_name,
                KeySchema=[
                    {'AttributeName': 'username', 'KeyType': 'HASH'},
                ],
                AttributeDefinitions=[
                    {'AttributeName': 'username', 'AttributeType': 'S'},
                ],
                BillingMode='PAY_PER_REQUEST',
            )
            
            table.wait_until_exists()
            self.logger.info(f"Created table: {table_name}")
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceInUseException':
                self.logger.info(f"Table {table_name} already exists")
            else:
                raise
    
    def _create_audit_table(self):
        """Create Audit Log table"""
        table_name = f'{self.table_prefix}-AuditLog'
        
        try:
            table = self.dynamodb.create_table(
                TableName=table_name,
                KeySchema=[
                    {'AttributeName': 'id', 'KeyType': 'HASH'},
                    {'AttributeName': 'timestamp', 'KeyType': 'RANGE'},
                ],
                AttributeDefinitions=[
                    {'AttributeName': 'id', 'AttributeType': 'S'},
                    {'AttributeName': 'timestamp', 'AttributeType': 'S'},
                    {'AttributeName': 'artifact_id', 'AttributeType': 'S'},
                    {'AttributeName': 'username', 'AttributeType': 'S'},
                ],
                GlobalSecondaryIndexes=[
                    {
                        'IndexName': 'ArtifactIndex',
                        'KeySchema': [
                            {'AttributeName': 'artifact_id', 'KeyType': 'HASH'},
                            {'AttributeName': 'timestamp', 'KeyType': 'RANGE'},
                        ],
                        'Projection': {'ProjectionType': 'ALL'},
                        'ProvisionedThroughput': {
                            'ReadCapacityUnits': 5,
                            'WriteCapacityUnits': 5
                        }
                    },
                    {
                        'IndexName': 'UserIndex',
                        'KeySchema': [
                            {'AttributeName': 'username', 'KeyType': 'HASH'},
                            {'AttributeName': 'timestamp', 'KeyType': 'RANGE'},
                        ],
                        'Projection': {'ProjectionType': 'ALL'},
                        'ProvisionedThroughput': {
                            'ReadCapacityUnits': 5,
                            'WriteCapacityUnits': 5
                        }
                    },
                ],
                BillingMode='PAY_PER_REQUEST',
            )
            
            table.wait_until_exists()
            self.logger.info(f"Created table: {table_name}")
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceInUseException':
                self.logger.info(f"Table {table_name} already exists")
            else:
                raise
    
    def _create_tokens_table(self):
        """Create Token Usage table"""
        table_name = f'{self.table_prefix}-Tokens'
        
        try:
            table = self.dynamodb.create_table(
                TableName=table_name,
                KeySchema=[
                    {'AttributeName': 'token_id', 'KeyType': 'HASH'},
                ],
                AttributeDefinitions=[
                    {'AttributeName': 'token_id', 'AttributeType': 'S'},
                    {'AttributeName': 'username', 'AttributeType': 'S'},
                ],
                GlobalSecondaryIndexes=[
                    {
                        'IndexName': 'UsernameIndex',
                        'KeySchema': [
                            {'AttributeName': 'username', 'KeyType': 'HASH'},
                        ],
                        'Projection': {'ProjectionType': 'ALL'},
                        'ProvisionedThroughput': {
                            'ReadCapacityUnits': 5,
                            'WriteCapacityUnits': 5
                        }
                    },
                ],
                BillingMode='PAY_PER_REQUEST',
            )
            
            table.wait_until_exists()
            self.logger.info(f"Created table: {table_name}")
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceInUseException':
                self.logger.info(f"Table {table_name} already exists")
            else:
                raise
    
    # PACKAGE/ARTIFACT OPERATIONS
    
    def create_package(self, package_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new package/artifact.
        
        Args:
            package_data: Dictionary with package information
            
        Returns:
            Created package data
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        
        item = {
            'id': package_data['id'],
            'artifact_type': package_data.get('artifact_type', 'model'),
            'name': package_data['name'],
            'version': package_data.get('version', '1.0.0'),
            'url': package_data.get('url'),
            's3_key': package_data.get('s3_key'),
            'readme_content': package_data.get('readme_content'),
            'metadata': package_data.get('metadata', {}),
            'scores': self._convert_floats_to_decimal(package_data.get('scores', {})),
            'net_score': Decimal(str(package_data.get('net_score', 0.0))),
            'is_deleted': False,
            'created_at': timestamp,
            'updated_at': timestamp,
            'created_by': package_data.get('created_by', 'system'),
        }
        
        try:
            if self.packages_table:
                self.packages_table.put_item(Item=item)
                self.logger.info(f"Created package: {item['id']}")
                return item
        except ClientError as e:
            self.logger.error(f"Error creating package: {e}")
            raise
    
    def get_package(self, package_id: str) -> Optional[Dict[str, Any]]:
        """Get package by ID"""
        try:
            response = self.packages_table.get_item(Key={'id': package_id})
            item = response.get('Item')
            
            if item and not item.get('is_deleted', False):
                return self._convert_decimals_to_float(item)
            return None
            
        except ClientError as e:
            self.logger.error(f"Error getting package {package_id}: {e}")
            return None
    
    def update_package(self, package_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update package"""
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # build update expression
        update_expr = "SET updated_at = :timestamp"
        expr_values = {':timestamp': timestamp}
        expr_names = {}
        
        for key, value in updates.items():
            if key in ['scores', 'metadata']:
                value = self._convert_floats_to_decimal(value)
            elif key == 'net_score':
                value = Decimal(str(value))
            
            # use expression attribute names to handle reserved keywords
            attr_name = f"#{key}"
            attr_value = f":{key}"
            
            update_expr += f", {attr_name} = {attr_value}"
            expr_names[attr_name] = key
            expr_values[attr_value] = value
        
        try:
            response = self.packages_table.update_item(
                Key={'id': package_id},
                UpdateExpression=update_expr,
                ExpressionAttributeNames=expr_names,
                ExpressionAttributeValues=expr_values,
                ReturnValues='ALL_NEW'
            )
            return self._convert_decimals_to_float(response.get('Attributes'))
            
        except ClientError as e:
            self.logger.error(f"Error updating package {package_id}: {e}")
            return None
    
    def delete_package(self, package_id: str, soft_delete: bool = True) -> bool:
        """Delete package (soft delete by default)"""
        try:
            if soft_delete:
                self.packages_table.update_item(
                    Key={'id': package_id},
                    UpdateExpression='SET is_deleted = :true, updated_at = :timestamp',
                    ExpressionAttributeValues={
                        ':true': True,
                        ':timestamp': datetime.now(timezone.utc).isoformat()
                    }
                )
            else:
                self.packages_table.delete_item(Key={'id': package_id})
            
            self.logger.info(f"Deleted package: {package_id} (soft={soft_delete})")
            return True
            
        except ClientError as e:
            self.logger.error(f"Error deleting package {package_id}: {e}")
            return False
    
    def query_packages_by_name(self, name: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Query packages by name using GSI"""
        try:
            response = self.packages_table.query(
                IndexName='NameIndex',
                KeyConditionExpression='#name = :name',
                ExpressionAttributeNames={'#name': 'name'},
                ExpressionAttributeValues={':name': name},
                Limit=limit,
                ScanIndexForward=False  # most recent first
            )
            
            items = [self._convert_decimals_to_float(item) 
                    for item in response.get('Items', [])
                    if not item.get('is_deleted', False)]
            return items
            
        except ClientError as e:
            self.logger.error(f"Error querying packages by name: {e}")
            return []
    
    def query_packages_by_type(self, artifact_type: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Query packages by artifact type"""
        try:
            response = self.packages_table.query(
                IndexName='TypeIndex',
                KeyConditionExpression='artifact_type = :type',
                ExpressionAttributeValues={':type': artifact_type},
                Limit=limit,
                ScanIndexForward=False
            )
            
            items = [self._convert_decimals_to_float(item) 
                    for item in response.get('Items', [])
                    if not item.get('is_deleted', False)]
            return items
            
        except ClientError as e:
            self.logger.error(f"Error querying packages by type: {e}")
            return []
    
    def scan_packages(self, filters: Optional[Dict] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Scan packages with optional filters.
        Use sparingly - scans are expensive.
        """
        try:
            scan_kwargs = {'Limit': limit}
            
            if filters:
                filter_expr = None
                expr_values = {}
                
                if 'name' in filters:
                    filter_expr = 'contains(#name, :name)'
                    expr_values[':name'] = filters['name']
                
                if 'artifact_type' in filters:
                    type_expr = 'artifact_type = :type'
                    expr_values[':type'] = filters['artifact_type']
                    filter_expr = type_expr if not filter_expr else f"{filter_expr} AND {type_expr}"
                
                if filter_expr:
                    scan_kwargs['FilterExpression'] = filter_expr
                    scan_kwargs['ExpressionAttributeValues'] = expr_values
                    if 'name' in filters:
                        scan_kwargs['ExpressionAttributeNames'] = {'#name': 'name'}
            
            response = self.packages_table.scan(**scan_kwargs)
            items = [self._convert_decimals_to_float(item) 
                    for item in response.get('Items', [])
                    if not item.get('is_deleted', False)]
            return items
            
        except ClientError as e:
            self.logger.error(f"Error scanning packages: {e}")
            return []
    
    # USER OPERATIONS
    
    def create_user(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new user"""
        timestamp = datetime.now(timezone.utc).isoformat()
        
        item = {
            'username': user_data['username'],
            'password_hash': user_data['password_hash'],
            'role': user_data.get('role', UserRole.SEARCHER.value),
            'created_at': timestamp,
            'is_active': True,
        }
        
        try:
            self.users_table.put_item(Item=item)
            self.logger.info(f"Created user: {item['username']}")
            return item
        except ClientError as e:
            self.logger.error(f"Error creating user: {e}")
            raise
    
    def get_user(self, username: str) -> Optional[Dict[str, Any]]:
        """Get user by username"""
        try:
            response = self.users_table.get_item(Key={'username': username})
            return response.get('Item')
        except ClientError as e:
            self.logger.error(f"Error getting user {username}: {e}")
            return None
    
    def update_user(self, username: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update user"""
        update_expr = "SET "
        expr_values = {}
        
        for i, (key, value) in enumerate(updates.items()):
            if i > 0:
                update_expr += ", "
            update_expr += f"{key} = :{key}"
            expr_values[f":{key}"] = value
        
        try:
            response = self.users_table.update_item(
                Key={'username': username},
                UpdateExpression=update_expr,
                ExpressionAttributeValues=expr_values,
                ReturnValues='ALL_NEW'
            )
            return response.get('Attributes')
        except ClientError as e:
            self.logger.error(f"Error updating user {username}: {e}")
            return None
    
    def delete_user(self, username: str) -> bool:
        """Delete user"""
        try:
            self.users_table.delete_item(Key={'username': username})
            self.logger.info(f"Deleted user: {username}")
            return True
        except ClientError as e:
            self.logger.error(f"Error deleting user {username}: {e}")
            return False
    
    def list_users(self, limit: int = 100) -> List[Dict[str, Any]]:
        """List all users"""
        try:
            response = self.users_table.scan(Limit=limit)
            return response.get('Items', [])
        except ClientError as e:
            self.logger.error(f"Error listing users: {e}")
            return []
    
    # AUDIT LOG OPERATIONS
    
    def log_audit(self, audit_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create audit log entry"""
        import uuid
        timestamp = datetime.now(timezone.utc).isoformat()
        
        item = {
            'id': str(uuid.uuid4()),
            'timestamp': timestamp,
            'artifact_id': audit_data.get('artifact_id'),
            'artifact_type': audit_data.get('artifact_type'),
            'action': audit_data['action'],
            'username': audit_data.get('username'),
            'details': audit_data.get('details', {}),
            'ip_address': audit_data.get('ip_address'),
        }
        
        try:
            self.audit_table.put_item(Item=item)
            return item
        except ClientError as e:
            self.logger.error(f"Error logging audit: {e}")
            raise
    
    def get_artifact_audit_trail(self, artifact_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get audit trail for an artifact"""
        try:
            response = self.audit_table.query(
                IndexName='ArtifactIndex',
                KeyConditionExpression='artifact_id = :artifact_id',
                ExpressionAttributeValues={':artifact_id': artifact_id},
                Limit=limit,
                ScanIndexForward=False  # Most recent first
            )
            return response.get('Items', [])
        except ClientError as e:
            self.logger.error(f"Error getting audit trail: {e}")
            return []
    
    def get_user_audit_trail(self, username: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get audit trail for a user"""
        try:
            response = self.audit_table.query(
                IndexName='UserIndex',
                KeyConditionExpression='username = :username',
                ExpressionAttributeValues={':username': username},
                Limit=limit,
                ScanIndexForward=False
            )
            return response.get('Items', [])
        except ClientError as e:
            self.logger.error(f"Error getting user audit trail: {e}")
            return []
    
    # TOKEN OPERATIONS
    
    def create_token(self, token_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create token usage record"""
        timestamp = datetime.now(timezone.utc).isoformat()
        
        item = {
            'token_id': token_data['token_id'],
            'username': token_data['username'],
            'call_count': 0,
            'created_at': timestamp,
            'last_used_at': timestamp,
        }
        
        try:
            self.tokens_table.put_item(Item=item)
            return item
        except ClientError as e:
            self.logger.error(f"Error creating token: {e}")
            raise
    
    def get_token(self, token_id: str) -> Optional[Dict[str, Any]]:
        """Get token by ID"""
        try:
            response = self.tokens_table.get_item(Key={'token_id': token_id})
            return response.get('Item')
        except ClientError as e:
            self.logger.error(f"Error getting token: {e}")
            return None
    
    def increment_token_usage(self, token_id: str) -> bool:
        """Increment token usage count"""
        try:
            self.tokens_table.update_item(
                Key={'token_id': token_id},
                UpdateExpression='SET call_count = call_count + :inc, last_used_at = :timestamp',
                ExpressionAttributeValues={
                    ':inc': 1,
                    ':timestamp': datetime.now(timezone.utc).isoformat()
                }
            )
            return True
        except ClientError as e:
            self.logger.error(f"Error incrementing token usage: {e}")
            return False
    
    def delete_token(self, token_id: str) -> bool:
        """Delete token"""
        try:
            self.tokens_table.delete_item(Key={'token_id': token_id})
            return True
        except ClientError as e:
            self.logger.error(f"Error deleting token: {e}")
            return False
    
    def get_user_tokens(self, username: str) -> List[Dict[str, Any]]:
        """Get all tokens for a user"""
        try:
            response = self.tokens_table.query(
                IndexName='UsernameIndex',
                KeyConditionExpression='username = :username',
                ExpressionAttributeValues={':username': username}
            )
            return response.get('Items', [])
        except ClientError as e:
            self.logger.error(f"Error getting user tokens: {e}")
            return []
    
    # SYSTEM OPERATIONS
    
    def reset_database(self):
        """Reset all tables to initial state"""
        try:
            # clear all packages
            self._clear_table(self.packages_table, 'id')
            
            # clear all users
            self._clear_table(self.users_table, 'username')
            
            # clear all audit logs
            self._clear_table(self.audit_table, 'id', 'timestamp')
            
            # clear all tokens
            self._clear_table(self.tokens_table, 'token_id')
            
            self.logger.info("Database reset completed")
            
        except Exception as e:
            self.logger.error(f"Error resetting database: {e}")
            raise
    
    def _clear_table(self, table, hash_key: str, range_key: str = None):
        """Clear all items from a table"""
        try:
            scan_kwargs = {}
            done = False
            start_key = None
            
            while not done:
                if start_key:
                    scan_kwargs['ExclusiveStartKey'] = start_key
                
                response = table.scan(**scan_kwargs)
                items = response.get('Items', [])
                
                with table.batch_writer() as batch:
                    for item in items:
                        key = {hash_key: item[hash_key]}
                        if range_key:
                            key[range_key] = item[range_key]
                        batch.delete_item(Key=key)
                
                start_key = response.get('LastEvaluatedKey', None)
                done = start_key is None
                
        except ClientError as e:
            self.logger.error(f"Error clearing table: {e}")
            raise
    
    # UTILITY METHODS
    
    def _convert_floats_to_decimal(self, obj):
        """Convert floats to Decimal for DynamoDB"""
        if isinstance(obj, float):
            return Decimal(str(obj))
        elif isinstance(obj, dict):
            return {k: self._convert_floats_to_decimal(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_floats_to_decimal(item) for item in obj]
        return obj
    
    def _convert_decimals_to_float(self, obj):
        """Convert Decimals back to float for JSON serialization"""
        if isinstance(obj, Decimal):
            return float(obj)
        elif isinstance(obj, dict):
            return {k: self._convert_decimals_to_float(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_decimals_to_float(item) for item in obj]
        return obj


# global instance
_db_service = None


def get_dynamodb_service() -> DynamoDBService:
    """Get or create global DynamoDB service instance"""
    global _db_service
    if _db_service is None:
        _db_service = DynamoDBService()
    return _db_service


def init_db():
    """Initialize database - creates tables and default admin user"""
    db_service = get_dynamodb_service()
    
    try:
        # create tables if they don't exist
        db_service.create_tables()
        
        # create the autograder's expected default admin user
        import bcrypt
        autograder_admin_username = "ece30861defaultadminuser"
        autograder_admin_password = "correcthorsebatterystaple123(!__+@**(A'\"`;DROP TABLE artifacts;"
        
        existing_admin = db_service.get_user(autograder_admin_username)
        
        if not existing_admin:
            password_hash = bcrypt.hashpw(autograder_admin_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            
            admin_user = db_service.create_user({
                'username': autograder_admin_username,
                'password_hash': password_hash,
                'role': UserRole.ADMIN.value
            })
            
            db_service.logger.info(f"✓ Created default admin user: {admin_user['username']}")
            print(f"✓ Created default admin user in DynamoDB: {admin_user['username']}")
        else:
            db_service.logger.info(f"✓ Default admin user already exists: {autograder_admin_username}")
            print(f"✓ Default admin user already exists in DynamoDB: {autograder_admin_username}")
            
    except Exception as e:
        db_service.logger.error(f"✗ Error initializing DynamoDB: {e}", exc_info=True)
        print(f"✗ Error initializing DynamoDB: {e}")
        raise  # Re-raise to prevent app from starting if init fails


if __name__ == '__main__':
    # for testing
    logging.basicConfig(level=logging.INFO)
    print("Initializing DynamoDB...")
    init_db()
    print("DynamoDB initialized successfully!")