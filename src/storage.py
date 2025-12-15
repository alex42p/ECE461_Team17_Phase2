"""
Simple storage system for MVP.
Stores package metadata in JSON files.
"""
# pyright: reportGeneralTypeIssues=false

import os
import json
import hashlib
import boto3 # type: ignore
import logging
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import tempfile
from typing import Optional, Dict, Any, List
from enum import Enum
# from huggingface_inspect import *

class S3Folders(Enum):
    """
    Every package will be stored in one of these folders
    in the S3 bucket depending on its artifact type
    """
    MODEL = "models/"
    DATASET = "datasets/"
    CODE = "codes/"

class S3Storage:
    """Simple file-based storage for packages."""
    
    def __init__(
            self, 
            storage_dir: str = "package_storage",
            aws_access_key: Optional[str] = None,
            aws_secret_key: Optional[str] = None,
            aws_region: Optional[str] = None,
            bucket_name: Optional[str] = None,
            hf_token: Optional[str] = None
    ):
        """Initialize storage directory."""
        self.__name__ = self.__class__.__name__

        # logger setup
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

        # create S3 client
        self.s3_client = boto3.client(
            's3', 
            # aws_access_key_id=aws_access_key,
            # aws_secret_access_key=aws_secret_key,
            region_name=aws_region,
        )
        self.bucket_name = bucket_name
        self.hf_token = hf_token
        if self.s3_client:
            self.logger.info("Created S3 client for region %s with bucket %s", aws_region, bucket_name)
        self.logger.info("Initialized S3Storage")
    
    def generate_package_id(self, name: str) -> str:
        """Generate unique package ID."""
        # sanitize name to avoid path separators in filenames
        safe_name = name.replace('/', '_').replace('\\', '_')
        pkg_id = hashlib.md5(safe_name.encode()).hexdigest()[:16]
        return pkg_id
    
    def save_package(
        self, 
        name: str,
        url: Optional[str] = None,
        artifact_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Save a package.
        
        Returns:
            Dict with package info:
            {
                "metadata": {
                    "id": package_id,
                    "name": name,
                    "type": artifact_type
                },
                "data": {
                    "url": url,
                    "download_url": presigned_url
                }
            }
        """
        # self.logger.debug("save_package called: name=%s url=%s", name, url)
        model_name = name.split('/')[-1]
        download_url = None

        # Sanitize name for filesystem use and check for existing package
        safe_name = model_name.replace('/', '_').replace('\\', '_')

        # Generate package ID
        package_id = self.generate_package_id(safe_name)
        self.logger.debug(f'Generated package ID: {package_id}')

        if url:
            # If URL is provided, clone the HF/Github repo, zip it up, and upload to S3
            try:
                s3_folder = self._get_s3_folder(artifact_type)
                zip_filename = f"{safe_name}.zip"
                s3_key = s3_folder + f"{package_id}/{zip_filename}"

                # upload using streaming method
                s3_uri = self._upload_huggingface_repo_streaming(
                    url=url,
                    model_id=name,
                    s3_key=s3_key,
                    artifact_type=artifact_type
                )

                download_url = self._generate_presigned_url(self.bucket_name, s3_key)

                self.logger.info(f'Generated presigned URL: {download_url}')
                self.logger.info(f'Uploaded zipped artifact to S3 as {s3_uri}')
            except Exception:
                self.logger.exception(f'Failed to upload zipped artifact for {model_name} to S3')

        package_data = {
            "metadata": {
                "id": package_id,
                "name": model_name,
                "type": artifact_type
            },
            "data": {
                "download_url": download_url,
                "url": url
            }
        }
        self.logger.info(f'Saved package {package_data}')

        return package_data

    def _upload_huggingface_repo_streaming(
        self,
        url: str,
        model_id: str,
        s3_key: str,
        artifact_type: Optional[str] = None,
        branch: str = "main",
        timeout: int = 600
    ) -> str:
        """
        Stream a HuggingFace repository directly to S3 without local storage.
        
        Uses git archive to stream zip output directly to S3 via multipart upload.
        Only creates a minimal bare clone (~100MB) regardless of repo size.
        
        Args:
            model_id: HuggingFace model ID (e.g., 'google-bert/bert-base-uncased')
            s3_key: Target S3 key for the zip file
            branch: Git branch to archive (default: 'main')
            timeout: Timeout for git clone in seconds (default: 600)
        
        Returns:
            S3 URI of uploaded zip file
            
        Raises:
            RuntimeError: If git operations fail
            subprocess.TimeoutExpired: If clone takes too long
        """
        if self.hf_token and artifact_type == "model":
            repo_url = f"https://hf:{self.hf_token}@huggingface.co/{model_id}"
        elif self.hf_token and artifact_type == "dataset":
            repo_url = f"https://hf:{self.hf_token}@huggingface.co/datasets/{model_id}"
        else:
            repo_url = url

        
        self.logger.debug(f"REPO URL:{repo_url}")
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            repo_path = tmpdir_path / "repo.git"
            
            # default branch to use for clone/archive; will fall back to 'master' if needed
            clone_branch = branch
            try:
                # Step 1: Shallow bare clone (minimal disk usage - only git metadata)
                self.logger.info(f"Cloning {model_id} (shallow bare clone) branch={clone_branch}")
                result = subprocess.run(
                    ["git", "clone", "--bare", "--depth=1", "--single-branch",
                    "--branch", clone_branch, repo_url, str(repo_path)],
                    check=True,
                    capture_output=True,
                    timeout=timeout,
                    text=True
                )
                self.logger.debug(f"Clone completed: {result.stdout}")
                
            except subprocess.TimeoutExpired:
                self.logger.error(f"Clone timeout for {model_id} after {timeout}s")
                raise RuntimeError(f"Repository clone timed out: {model_id}")
            except subprocess.CalledProcessError as e:
                # If the requested branch fails, try using 'master' as a fallback
                if clone_branch.lower() != 'master':
                    self.logger.warning(
                        f"Clone failed for {model_id} using branch {clone_branch}: {e.stderr.strip()}. Trying 'master' as fallback."
                    )
                    clone_branch = 'master'
                    try:
                        result = subprocess.run(
                            ["git", "clone", "--bare", "--depth=1", "--single-branch",
                            "--branch", clone_branch, repo_url, str(repo_path)],
                            check=True,
                            capture_output=True,
                            timeout=timeout,
                            text=True
                        )
                        self.logger.info(f"Clone succeeded for {model_id} using fallback branch {clone_branch}")
                        self.logger.debug(f"Clone completed: {result.stdout}")
                    except subprocess.CalledProcessError as e2:
                        self.logger.error(f"Clone failed for {model_id} using fallback branch {clone_branch}: {e2.stderr}")
                        raise RuntimeError(f"Git clone failed: {e2.stderr}")
                else:
                    self.logger.error(f"Clone failed for {model_id}: {e.stderr}")
                    raise RuntimeError(f"Git clone failed: {e.stderr}")
            
            # Step 2: Stream git archive directly to S3
            self.logger.info(f"Streaming archive to S3: {s3_key}")
            
            try:
                # Start git archive process
                process = subprocess.Popen(
                    ["git", "--git-dir", str(repo_path), "archive",
                    "--format=zip", clone_branch],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                
                # upload_fileobj automatically handles multipart upload for large streams
                # It will buffer and upload in chunks (default 8MB chunks)
                self.s3_client.upload_fileobj(
                    process.stdout,
                    self.bucket_name,
                    s3_key,
                    ExtraArgs={
                        'ContentType': 'application/zip',
                        'Metadata': {
                            'model_id': model_id,
                            'source': 'huggingface' if artifact_type == 'code' else 'github',
                        }
                    }
                )
                
                # Wait for git archive to finish and check for errors
                _, stderr = process.communicate()
                
                if process.returncode != 0:
                    error_msg = stderr.decode() if stderr else "Unknown error"
                    self.logger.error(f"git archive failed: {error_msg}")
                    raise RuntimeError(f"git archive failed: {error_msg}")
                
                s3_uri = f"s3://{self.bucket_name}/{s3_key}"
                self.logger.info(f"Upload complete: {s3_uri}")
                return s3_uri
                
            except Exception as e:
                self.logger.exception(f"Error during archive/upload for {model_id}")
                # Attempt to clean up partial upload
                try:
                    self.s3_client.delete_object(Bucket=self.bucket_name, Key=s3_key)
                    self.logger.debug(f"Cleaned up partial upload at {s3_key}")
                except Exception:
                    pass  # Cleanup is best-effort
                raise

    
    def _get_s3_folder(self, artifact_type: Optional[str]) -> str:
        """
        Get the S3 folder prefix based on artifact type.
        Defaults to 'models/' if type is unknown.
        """
        if artifact_type == "model":
            return S3Folders.MODEL.value
        elif artifact_type == "dataset":
            return S3Folders.DATASET.value
        elif artifact_type == "code":
            return S3Folders.CODE.value
        else:
            return S3Folders.MODEL.value  # default folder
        
    def _generate_presigned_url(self, bucket_name, s3_key, expiration=604800) -> Optional[str]:
        """Generate a presigned URL to download an S3 object."""
        try:
            url: str = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': bucket_name, 'Key': s3_key},
                ExpiresIn=expiration
            )
            self.logger.debug(f"Generated presigned URL for {s3_key}: {url}")
            return url
        except Exception as e:
            self.logger.exception(f"Error generating presigned URL: {e}")
            return None
    
    def generate_presigned_url(self, s3_key: Optional[str], expiration: int = 3600) -> Optional[str]:
        """
        Generate a pre-signed S3 URL for downloading an artifact.
        
        Args:
            s3_key: S3 object key
            expiration: URL expiration time in seconds (default 1 hour)
        
        Returns:
            Pre-signed URL or None if bucket not configured
        """
        if not self.bucket_name or not s3_key:
            return None
        
        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket_name, 'Key': s3_key},
                ExpiresIn=expiration
            )
            self.logger.debug("Generated presigned URL for %s", s3_key)
            return url
        except Exception as e:
            self.logger.exception("Failed to generate presigned URL for %s: %s", s3_key, e)
            return None
    
    def clear_all_s3_objects(self):
        """
        Delete all objects from the S3 bucket (for reset endpoint).
        """
        if not self.bucket_name:
            self.logger.warning("clear_all_s3_objects: S3 bucket name not configured, skipping S3 cleanup")
            return
        
        try:
            self.logger.info("clear_all_s3_objects: starting cleanup of S3 bucket %s", self.bucket_name)
            
            # List all objects in the bucket
            paginator = self.s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=self.bucket_name)
            
            deleted_count = 0
            for page in pages:
                if 'Contents' in page:
                    objects = [{'Key': obj['Key']} for obj in page['Contents']]
                    if objects:
                        # Delete objects in batches (max 1000 per request)
                        response = self.s3_client.delete_objects(
                            Bucket=self.bucket_name,
                            Delete={'Objects': objects}
                        )
                        deleted_count += len(objects)
                        if 'Errors' in response and response['Errors']:
                            for error in response['Errors']:
                                self.logger.error("clear_all_s3_objects: failed to delete %s: %s", 
                                                 error.get('Key'), error.get('Message'))
            
            self.logger.info("clear_all_s3_objects: deleted %d objects from S3 bucket %s", deleted_count, self.bucket_name)
            
        except Exception as e:
            self.logger.exception("clear_all_s3_objects: error clearing S3 bucket %s: %s", self.bucket_name, e)
            # Don't raise - allow reset to continue even if S3 cleanup fails
