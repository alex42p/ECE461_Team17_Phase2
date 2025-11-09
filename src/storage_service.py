import boto3
import logging
from typing import Optional, Dict, Any
from botocore.exceptions import ClientError
from botocore.config import Config
import hashlib
import json
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class StorageService:
    """Handles S3 operations with error handling"""

    def __init__(self, bucket_name: str, region: str = 'us-east-1'):
        self.bucket_name = bucket_name
        self.region = region

        # config retry strategy
        config = Config(
            region_name = region,
            retries = {
                'max-attempts': 3,
                'mode': 'adaptive'
            }
        )

        self.s3_client = boto3.client('s3', config=config)
        self.s3_resource = boto3.resource('s3', config=config)

        # create buckets if they don't exist
        self._ensure_buckets()

    def _ensure_buckets(self):
        """Ensure S3 buckets exist with proper config"""

        buckets = {
            f"{self.bucket_name}-models": {
                'lifecycle': True,
                'versioning': True
            },
            f"{self.bucket_name}-datasets": {
                'lifecycle': True,
                'versioning': True
            },
            f"{self.bucket_name}-code": {
                'lifecycle': False,
                'versioning': True
            }
        }

        for bucket_name, config in buckets.items():
            try:
                self.s3_client.head_bucket(Bucket=bucket_name)
                logger.info(f"Bucket {bucket_name} already exists.")
            except ClientError as e:
                self._create_bucket(bucket_name, config)

    def _create_bucket(self, bucket_name: str, config: Dict):
        """Create S3 bucket with config"""

        try:

            if self.region == 'us-east-1':
                self.s3_client.create_bucket(Bucket=bucket_name)
            else:
                self.s3_client.create_bucket(
                    Bucket=bucket_name,
                    CreateBucketConfiguration={'LocationConstraint': self.region}
                )
            
            # en versioning
            if config.get('versioning'):
                self.s3_client.put_bucket_versioning(
                    Bucket=bucket_name,
                    VersioningConfiguration={'Status': 'Enabled'}
                )

            # set lifecycle policy
            if config.get('lifecycle'):
                self._set_lifecycle_policy(bucket_name)

            logger.info(f"Bucket {bucket_name} created successfully.")
       
        except ClientError as e:

            logger.error(f"Error creating bucket {bucket_name}: {e}")
            raise

    def _set_lifecycle_policy(self, bucket_name: str):
        """Set lifecycle policy to move old versions to Glacier"""

        lifecycle_policy = {
            'Rules': [{
                'ID': 'Archive old versions',
                'Status': 'Enabled',
                'NoncurrentVersionTransitions': [{
                    'NoncurrentDays': 30,
                    'StorageClass': 'GLACIER'
                }],
                'NoncurrentVersionExpiration': {
                    'NoncurrentDays': 365
                }
            }]
        }

        self.s3_client.put_bucket_lifecycle_configuration(
            Bucket=bucket_name,
            LifecycleConfiguration=lifecycle_policy
        )

    def upload_artifact(self, artifact_type: str, artifact_id: str,
                        data: bytes, metadata: Dict = None) -> str:
        """Upload artifact to S3 with metadata"""

        bucket = f"{self.bucket_name}-{artifact_type}s"
        key = f"{artifact_id}/{datetime.utcnow().isoformat()}/artifact.tar.gz"

        try:

            # calculate checksum
            checksum = hashlib.sha256(data).hexdigest()

            # prepare metadata
            s3_metadata = {
                'artifact_id': artifact_id,
                'artifact_type': artifact_type,
                'checksum': checksum,
                'upload_timestamp': datetime.utcnow().isoformat()
            }

            if metadata:
                s3_metadata.update(metadata)

            # upload with server side encryption
            self.s3_client.put_object(
                Bucket=bucket,
                Key=key,
                Body=data,
                Metadata={k: str(v) for k, v in s3_metadata.items()},
                ServerSideEncryption='AES256',
                ContentType='application/gzip'
            )

            logger.info(f"Uploaded artifact {artifact_id} to {bucket}/{key}")
            return key

        except ClientError as e:
            logger.error(f"Error uploading artifact {artifact_id}: {e}")
            raise

    def generate_presigned_url(self, artifact_type: str, key: str,
                               expiration: int = 3600) -> str:
        """Generate presigned URL for artifact download"""

        bucket = f"{self.bucket_name}-{artifact_type}s"

        try:

            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': bucket, 'Key': key},
                ExpiresIn=expiration
            )
            return url
        
        except ClientError as e:

            logger.error(f"Error generating presigned URL for {key}: {e}")
            raise

    def delete_artifact(self, artifact_type: str, key: str, soft_delete: bool = True) -> bool:
        """Delete artifact from S3"""

        bucket = f"{self.bucket_name}-{artifact_type}s"

        try:

            if soft_delete:
                # move to Glacier instead of deleting
                copy_source = {'Bucket': bucket, 'Key': key}
                archive_key = f"archived/{key}"

                self.s3_client.copy_object(
                    Bucket=bucket,
                    CopySource=copy_source,
                    Key=archive_key,
                    StorageClass='GLACIER',
                    Metadata={'archived_date': datetime.utcnow().isoformat()},
                )

                # delete original
                self.s3_client.delete_object(Bucket=bucket, Key=key)
                logger.info(f"Archived artifact to Glacier: {archive_key}")

            else:
                # hard delete
                self.s3_client.delete_object(Bucket=bucket, Key=key)
                logger.info(f"Deleted artifact: {bucket}/{key}")

        except ClientError as e:

            logger.error(f"Error deleting artifact {key}: {e}")
            raise

    def clear_all_buckets(self):
        """Clear all artifacts from S3"""

        for artifact_type in ['model', 'dataset', 'code']:
            bucket = f"{self.bucket_name}-{artifact_type}s"

            try:
                # delete all objects
                bucket_resource = self.s3_resource.Bucket(bucket)
                bucket_resource.objects.all().delete()

                # delete all versions
                bucket_resource.object_versions.all().delete()

                logger.info(f"Cleared all artifacts from bucket: {bucket}")

            except ClientError as e:

                logger.error(f"Error clearing bucket {bucket}: {e}")
                raise
