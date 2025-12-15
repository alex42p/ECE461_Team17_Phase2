"""
DynamoDB Service for Package Registry
"""
# mypy: ignore-errors
# pyright: reportAttributeAccessIssue=false, reportArgumentType=false

import boto3
import os
import re
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

    def __init__(
            self,
            aws_access_key: Optional[str],
            aws_secret_key: Optional[str],
            region_name: Optional[str] = None,
            endpoint_url: Optional[str] = None # for local development with DynamoDB Local
            ):
        """
        Initialize DynamoDB service.
        
        Args:
            aws_access_key: AWS access key ID
            aws_secret_key: AWS secret access key
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

            # Optionally attach CloudWatch handler when explicitly enabled
            try:
                    import watchtower
                    session = boto3.session.Session(
                        # aws_access_key_id=self.aws_access_key,
                        # aws_secret_access_key=self.aws_secret_key,
                        region_name=self.region_name
                    )
                    cw_handler = watchtower.CloudWatchLogHandler(
                        boto3_session=session,
                        log_group='ECE461-Team17',
                        stream_name=f"{self.__name__}"
                    )
                    cw_handler.setLevel(logging.INFO)
                    cw_handler.setFormatter(fmt)
                    # Avoid adding the same handler multiple times
                    if not any(isinstance(h, watchtower.CloudWatchLogHandler) for h in self.logger.handlers):
                        self.logger.addHandler(cw_handler)
                    self.logger.info('CloudWatch logging enabled for DynamoDBService')
            except Exception as e:
                self.logger.warning(f'Could not initialize CloudWatch handler: {e}')

        self.region_name = region_name
        self.aws_access_key = aws_access_key
        self.aws_secret_key = aws_secret_key
        self.endpoint_url = endpoint_url

        if not all([self.region_name, self.aws_access_key, self.aws_secret_key]):
            self.logger.error("AWS credentials or region not properly set.")
            raise ValueError("AWS credentials or region not properly set.")

        self.dynamodb = boto3.resource(
            'dynamodb',
            region_name=self.region_name,
            aws_access_key_id=self.aws_access_key,
            aws_secret_access_key=self.aws_secret_key
        )
        self.logger.info(f"Connected to DynamoDB in region {self.region_name}")
    
        self.table_prefix = 'ECE461-Team17'
        
        self._initialize_tables()
    
    def _initialize_tables(self):
        """Initialize DynamoDB table references"""
        try:
            self.packages_table = self.dynamodb.Table(f'{self.table_prefix}-Packages') 
            self.logger.info(f"Successfully connected to {self.packages_table.table_name} table - Status: {self.packages_table.table_status}")
        except Exception as e:
            self.logger.error(f"Error initializing tables: {e}")
            raise

    
    # PACKAGE/ARTIFACT OPERATIONS
    
    def create_package(self, package_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Create a new package/artifact.
        
        Args:
            package_data: Dictionary with package information
            {
                "metadata": 
                {
                    "id": "package-id",
                    "type": "model",
                    "name": "My Model"
                },
                "data": 
                {
                    "url": "huggingcface-url",
                    "download_url": "presigned-url",
                }
                "scores": 
                {
                    "net_score": 0.85, 
                    "net_score_latency": 0.9, ...
                },
                "created_at": timestamp,
                "is_deleted": False
                "readme": "Package readme text"
                "cost": 
            }
            
        Returns:
            Created package data
        """
        # timestamp = datetime.now(timezone.utc).isoformat()
        item = package_data.copy()
        item['cost'] = self._convert_floats_to_decimal(item.get('cost', {}))
        self.logger.info(f"Creating package with ID: {item.get('metadata').get('id')}") # type: ignore
        
        try:
            if self.packages_table:
                self.packages_table.put_item(Item=item)
                self.logger.info(f"Created package: {item}")
                return item
        except ClientError as e:
            self.logger.error(f"Error creating package: {e}")
            raise
    
    def get_package(self, package_id: str) -> Optional[Dict[str, Any]]:
        """Get package by ID"""
        try:
            self.logger.debug(f"Fetching package with ID: {package_id}") 
            response = self.packages_table.get_item(Key={'id': package_id})
            self.logger.debug(f"Get package response: {response}")
            item = response.get('Item')
            self.logger.debug(f"Fetched package item: {item}")
            if item and not item.get('is_deleted', False):
                return self._convert_decimals_to_float(item)
            return None
            
        except ClientError as e:
            self.logger.error(f"Error getting package {package_id}: {e}")
            return None
    
    def get_all_packages(self):
        """Get all packages from DynamoDB."""
        try:
            response = self.packages_table.scan()
            return [self._convert_decimals_to_float(item) for item in response.get('Items', [])]
        except Exception as e:
            self.logger.error(f"Error getting all packages: {e}")
            return []
    
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
    
    # def scan_packages(self, filters: Optional[Dict] = None, limit: int = 100) -> List[Dict[str, Any]]:
    #     """
    #     Scan packages with optional filters.
    #     Use sparingly - scans are expensive.
    #     """
    #     try:
    #         scan_kwargs = {'Limit': limit}
            
    #         if filters:
    #             filter_expr = None
    #             expr_values = {}
                
    #             if 'name' in filters:
    #                 filter_expr = 'contains(#name, :name)'
    #                 expr_values[':name'] = filters['name']
                
    #             if 'artifact_type' in filters:
    #                 type_expr = 'artifact_type = :type'
    #                 expr_values[':type'] = filters['artifact_type']
    #                 filter_expr = type_expr if not filter_expr else f"{filter_expr} AND {type_expr}"
                
    #             if filter_expr:
    #                 scan_kwargs['FilterExpression'] = filter_expr
    #                 scan_kwargs['ExpressionAttributeValues'] = expr_values
    #                 if 'name' in filters:
    #                     scan_kwargs['ExpressionAttributeNames'] = {'#name': 'name'}
            
    #         response = self.packages_table.scan(**scan_kwargs)
    #         items = [self._convert_decimals_to_float(item) 
    #                 for item in response.get('Items', [])
    #                 if not item.get('is_deleted', False)]
    #         return items
            
    #     except ClientError as e:
    #         self.logger.error(f"Error scanning packages: {e}")
    #         return []
    
    # SYSTEM OPERATIONS
    
    def reset_database(self):
        """Reset all tables to initial state"""
        try:
            # clear all packages
            self._clear_table(self.packages_table, 'id')
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
    
    def _convert_floats_to_decimal(self, obj: Any) -> Any:
        """Convert floats to Decimal for DynamoDB"""
        if isinstance(obj, float):
            return Decimal(str(obj))
        elif isinstance(obj, dict):
            return {k: self._convert_floats_to_decimal(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_floats_to_decimal(item) for item in obj]
        return obj
    
    def _convert_decimals_to_float(self, obj: Any) -> Any:
        """Convert Decimals back to float for JSON serialization"""
        if isinstance(obj, Decimal):
            return float(obj)
        elif isinstance(obj, dict):
            return {k: self._convert_decimals_to_float(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_decimals_to_float(item) for item in obj]
        return obj

    def search_packages_by_regex(self, pattern: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Search packages by regex pattern on metadata-name field OR readme field.
        
        Args:
            pattern: Regular expression pattern to match package names
            limit: Maximum number of results to return
            
        Returns:
            List of matching packages
        """        
        try:
            regex = re.compile(pattern)
        except re.error as e:
            self.logger.error(f"Invalid regex pattern: {e}")
            return []
        
        try:
            response = self.packages_table.scan()
            items = []
            for item in response.get('Items', []):
                name = item.get('name', '')
                if regex.search(name) and not item.get('is_deleted', False):
                    items.append(self._convert_decimals_to_float(item))
                    if len(items) >= limit:
                        break
                elif regex.search(item.get('readme', '')) and not item.get('is_deleted', False):
                    items.append(self._convert_decimals_to_float(item))
                    if len(items) >= limit:
                        break
            return items
            
        except ClientError as e:
            self.logger.error(f"Error searching packages by regex: {e}")
            return []