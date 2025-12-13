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
            bucket_name: Optional[str] = None
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

        # Always resolve to absolute path to avoid working directory issues
        # Convert to Path if it's a string, then resolve to absolute
        if isinstance(storage_dir, str):
            self.storage_dir = Path(storage_dir).resolve()
        else:
            self.storage_dir = Path(storage_dir).resolve()
        self.metadata_dir = (self.storage_dir / "metadata").resolve()

        # create S3 client
        self.s3_client = boto3.client(
            's3', 
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key,
            region_name=aws_region,
        )
        self.bucket_name = bucket_name

        if self.s3_client:
            self.logger.info("Created S3 client for region %s with bucket %s", aws_region, bucket_name)
        
        # Create directories if they don't exist
        # self.metadata_dir.mkdir(parents=True, exist_ok=True)

        self.logger.info("Initialized S3Storage")
    
    
    def generate_package_id(self, name: str) -> str:
        """Generate unique package ID."""
        # sanitize name to avoid path separators in filenames
        safe_name = name.replace('/', '_').replace('\\', '_')
        # unique_str = f"{safe_name}-{datetime.now(timezone.utc).isoformat()}"
        # hash_suffix = hashlib.md5(unique_str.encode()).hexdigest()[:16]
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
                
                # clone repo to a local tempdir
                # model_dir: Path = clone_model_repo(name)

                # zip up the cloned repo
                # shutil.make_archive(base_name=safe_name, format='zip', root_dir=model_dir)

                # upload to S3
                # s3_uri = self.upload_file_to_s3(zip_filename, s3_key)

                # upload using streaming method
                s3_uri = self._upload_huggingface_repo_streaming(
                    model_id=name,
                    s3_key=s3_key
                )

                download_url = self._generate_presigned_url(self.bucket_name, s3_key)
                
                # clean up local files
                # clean_up_cache(model_dir)

                # os.remove(zip_filename)
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
        model_id: str,
        s3_key: str,
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
        repo_url = f"https://huggingface.co/{model_id}"
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            repo_path = tmpdir_path / "repo.git"
            
            try:
                # Step 1: Shallow bare clone (minimal disk usage - only git metadata)
                self.logger.info(f"Cloning {model_id} (shallow bare clone)")
                result = subprocess.run(
                    ["git", "clone", "--bare", "--depth=1", "--single-branch",
                    "--branch", branch, repo_url, str(repo_path)],
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
                self.logger.error(f"Clone failed for {model_id}: {e.stderr}")
                raise RuntimeError(f"Git clone failed: {e.stderr}")
            
            # Step 2: Stream git archive directly to S3
            self.logger.info(f"Streaming archive to S3: {s3_key}")
            
            try:
                # Start git archive process
                process = subprocess.Popen(
                    ["git", "--git-dir", str(repo_path), "archive",
                    "--format=zip", branch],
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
                            'source': 'huggingface'
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
            self.logger.error(f"Error generating presigned URL: {e}")
            return None

    # REMOVE LATER - replaced by streaming upload above
    def upload_file_to_s3(self, filename: str, s3_key: str) -> str:
        """
        Upload a local file to S3 and return the S3 URI (s3://bucket/key).
        """
        if not self.bucket_name:
            raise ValueError("S3 bucket name is not configured (S3_BUCKET_NAME).")
        file_path = Path("./cache" + filename)
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {filename}")

        try:
            self.logger.debug("upload_file_to_s3: uploading %s to %s/%s", file_path, self.bucket_name, s3_key)
            # boto3 will stream from disk; this requires valid AWS credentials and permissions
            self.s3_client.upload_file(str(file_path), self.bucket_name, s3_key)
            s3_uri = f"s3://{self.bucket_name}/{s3_key}"
            self.logger.info("upload_file_to_s3: uploaded to %s", s3_uri)
            return s3_uri
        except Exception as e:
            self.logger.exception("upload_file_to_s3: failed to upload %s to s3://%s/%s: %s", file_path, self.bucket_name, s3_key, e)
            raise
    
    # REMOVE LATER - NEED TO REDESIGN
    def get_package(self, package_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve package by ID.
        
        Returns:
            Package data or None if not found or deleted
        """
        metadata_file = self.metadata_dir / f"{package_id}.json"
        try:
            self.logger.debug("get_package: lookup %s", metadata_file.name)
        except Exception:
            pass

        if not metadata_file.exists():
            self.logger.info("get_package: package %s not found", package_id)
            return None

        try:
            with open(metadata_file, "r") as f:
                data = json.load(f)
                # Filter out deleted artifacts
                if data.get("is_deleted", False):
                    self.logger.info("get_package: package %s is deleted", package_id)
                    return None
                self.logger.debug("get_package: loaded %s", metadata_file.name)
                return data
        except Exception as e:
            self.logger.exception("get_package: failed to read %s: %s", metadata_file.name, e)
            return None
    
    # REDESIGN TO ACCESS DYNAMO LATER
    def search_by_regex(self, regex_pattern: str) -> List[Dict[str, Any]]:
        """
        Search packages by regex pattern on name.
        
        Args:
            regex_pattern: Regular expression to match against package names
        
        Returns:
            List of matching packages, sorted by net score (descending)
        """
        import re

        # try:
        #     self.logger.debug("search_by_regex: pattern=%s", regex_pattern)
        # except Exception:
        #     pass

        try:
            pattern = re.compile(regex_pattern, re.IGNORECASE)
        except re.error as e:
            self.logger.exception("search_by_regex: invalid regex %s: %s", regex_pattern, e)
            raise ValueError(f"Invalid regex pattern: {e}")

        results = []

        # Scan all package metadata files
        for metadata_file in self.metadata_dir.glob("*.json"):
            try:
                with open(metadata_file, "r") as f:
                    package_data = json.load(f)

                # Skip deleted artifacts
                if package_data.get("is_deleted", False):
                    continue

                # Check if name matches pattern
                if pattern.search(package_data.get("name", "")):
                    results.append(package_data)

            except Exception as e:
                self.logger.warning("search_by_regex: error reading %s: %s", metadata_file.name, e)
                continue

        # Sort by net score (highest first)
        results.sort(
            key=lambda x: x.get("scores", {}).get("net_score", {}).get("value", 0),
            reverse=True
        )

        # self.logger.debug("search_by_regex: found %d matches for pattern %s", len(results), regex_pattern)
        return results
    
    def get_packages_by_name(self, name: str) -> List[Dict[str, Any]]:
        """
        Get all packages with exact name match.
        
        Args:
            name: Exact package name to search for
        
        Returns:
            List of packages with matching name (excluding deleted)
        """
        results = []
        for metadata_file in self.metadata_dir.glob("*.json"):
            try:
                with open(metadata_file, "r") as f:
                    package_data = json.load(f)
                    if package_data.get("name") == name and not package_data.get("is_deleted", False):
                        results.append(package_data)
            except Exception as e:
                self.logger.warning("get_packages_by_name: error reading %s: %s", metadata_file.name, e)
                continue
        
        # Sort by created_at (newest first)
        results.sort(
            key=lambda x: x.get("created_at", ""),
            reverse=True
        )
        return results
    
    def query_packages(self, artifact_type: Optional[str] = None, name_filter: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Query packages with optional filters.
        
        Args:
            artifact_type: Filter by artifact type (model, dataset, code)
            name_filter: Filter by name (partial match)
            limit: Maximum number of results
        
        Returns:
            List of matching packages (excluding deleted)
        """
        results = []
        for metadata_file in self.metadata_dir.glob("*.json"):
            try:
                with open(metadata_file, "r") as f:
                    package_data = json.load(f)
                    
                    # Skip deleted artifacts
                    if package_data.get("is_deleted", False):
                        continue
                    
                    # Apply filters
                    if artifact_type and package_data.get("artifact_type") != artifact_type:
                        continue
                    if name_filter and name_filter.lower() not in package_data.get("name", "").lower():
                        continue
                    
                    results.append(package_data)
            except Exception as e:
                self.logger.warning("query_packages: error reading %s: %s", metadata_file.name, e)
                continue
        
        # Sort by created_at (newest first)
        results.sort(
            key=lambda x: x.get("created_at", ""),
            reverse=True
        )
        
        return results[:limit]
    
    def generate_presigned_url(self, s3_key: str, expiration: int = 3600) -> Optional[str]:
        """
        Generate a pre-signed S3 URL for downloading an artifact.
        
        Args:
            s3_key: S3 object key
            expiration: URL expiration time in seconds (default 1 hour)
        
        Returns:
            Pre-signed URL or None if bucket not configured
        """
        if not self.bucket_name:
            return None
        
        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket_name, 'Key': s3_key},
                ExpiresIn=expiration
            )
            self.logger.debug("generate_presigned_url: generated URL for %s", s3_key)
            return url
        except Exception as e:
            self.logger.exception("generate_presigned_url: failed to generate URL for %s: %s", s3_key, e)
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

    # def upload_huggingface_repo(
    #     self,
    #     model_id: str,
    #     package_id: str,
    #     branch: str = "main"
    # ) -> str:
    #     """
    #     Clone and upload a HuggingFace repository directly to S3.
        
    #     Uses git archive to stream the repo without local storage.
        
    #     Args:
    #         model_id: HuggingFace model ID (e.g., 'google-bert/bert-base-uncased')
    #         package_id: Your internal package ID
    #         branch: Git branch to archive (default: 'main')
        
    #     Returns:
    #         S3 URI of uploaded zip file
    #     """
    #     import subprocess
    #     import tempfile
        
    #     # Sanitize model_id for use in S3 key
    #     safe_model_id = model_id.replace('/', '_')
    #     s3_key = f"packages/{package_id}/{safe_model_id}.zip"
        
    #     repo_url = f"https://huggingface.co/{model_id}"
        
    #     with tempfile.TemporaryDirectory() as tmpdir:
    #         tmpdir_path = Path(tmpdir)
    #         repo_path = tmpdir_path / "repo.git"
            
    #         try:
    #             # Step 1: Shallow bare clone (minimal disk usage)
    #             self.logger.info(f"Cloning {model_id} (shallow)")
    #             subprocess.run(
    #                 ["git", "clone", "--bare", "--depth=1", "--single-branch",
    #                 "--branch", branch, repo_url, str(repo_path)],
    #                 check=True,
    #                 capture_output=True,
    #                 timeout=300  # 5 minute timeout
    #             )
                
    #             # Step 2: Stream git archive directly to S3
    #             self.logger.info(f"Streaming archive to S3: {s3_key}")
                
    #             # Start multipart upload for reliability
    #             mpu = self.s3_client.create_multipart_upload(
    #                 Bucket=self.bucket_name,
    #                 Key=s3_key,
    #                 ContentType='application/zip',
    #                 Metadata={
    #                     'model_id': model_id,
    #                     'package_id': package_id
    #                 }
    #             )
                
    #             upload_id = mpu['UploadId']
    #             parts = []
    #             part_number = 1
    #             chunk_size = 50 * 1024 * 1024  # 50MB chunks
                
    #             try:
    #                 # Start git archive process
    #                 process = subprocess.Popen(
    #                     ["git", "--git-dir", str(repo_path), "archive",
    #                     "--format=zip", branch],
    #                     stdout=subprocess.PIPE,
    #                     stderr=subprocess.PIPE
    #                 )
                    
    #                 # Stream output to S3 in chunks
    #                 while True:
    #                     chunk = process.stdout.read(chunk_size) # type: ignore
    #                     if not chunk:
    #                         break
                        
    #                     part = self.s3_client.upload_part(
    #                         Bucket=self.bucket_name,
    #                         Key=s3_key,
    #                         PartNumber=part_number,
    #                         UploadId=upload_id,
    #                         Body=chunk
    #                     )
                        
    #                     parts.append({
    #                         'PartNumber': part_number,
    #                         'ETag': part['ETag']
    #                     })
                        
    #                     part_number += 1
    #                     self.logger.debug(f"Uploaded part {part_number}")
                    
    #                 # Wait for git archive to finish
    #                 _, stderr = process.communicate()
                    
    #                 if process.returncode != 0:
    #                     raise RuntimeError(f"git archive failed: {stderr.decode()}")
                    
    #                 # Complete multipart upload
    #                 self.s3_client.complete_multipart_upload(
    #                     Bucket=self.bucket_name,
    #                     Key=s3_key,
    #                     UploadId=upload_id,
    #                     MultipartUpload={'Parts': parts}
    #                 )
                    
    #                 s3_uri = f"s3://{self.bucket_name}/{s3_key}"
    #                 self.logger.info(f"Successfully uploaded {model_id} to {s3_uri}")
    #                 return s3_uri
                    
    #             except Exception as e:
    #                 # Abort multipart upload on error
    #                 self.logger.error(f"Upload failed, aborting: {e}")
    #                 self.s3_client.abort_multipart_upload(
    #                     Bucket=self.bucket_name,
    #                     Key=s3_key,
    #                     UploadId=upload_id
    #                 )
    #                 raise
                    
    #         except subprocess.TimeoutExpired:
    #             self.logger.error(f"Clone timeout for {model_id}")
    #             raise RuntimeError(f"Repository clone timed out: {model_id}")
    #         except Exception as e:
    #             self.logger.exception(f"Error uploading {model_id}: {e}")
    #             raise


    # def upload_huggingface_repo_simple(
    #     self,
    #     model_id: str,
    #     package_id: str,
    #     branch: str = "main"
    # ) -> str:
    #     """
    #     Simpler version using upload_fileobj (auto-handles multipart).
    #     Better for most cases unless you need fine control.
    #     """
    #     import subprocess
    #     import tempfile
        
    #     safe_model_id = model_id.replace('/', '_')
    #     s3_key = f"packages/{package_id}/{safe_model_id}.zip"
    #     repo_url = f"https://huggingface.co/{model_id}"
        
    #     with tempfile.TemporaryDirectory() as tmpdir:
    #         tmpdir_path = Path(tmpdir)
    #         repo_path = tmpdir_path / "repo.git"
            
    #         # Shallow clone
    #         self.logger.info(f"Cloning {model_id}")
    #         subprocess.run(
    #             ["git", "clone", "--bare", "--depth=1", "--single-branch",
    #             "--branch", branch, repo_url, str(repo_path)],
    #             check=True,
    #             capture_output=True,
    #             timeout=300
    #         )
            
    #         # Stream git archive to S3
    #         self.logger.info(f"Uploading to S3: {s3_key}")
    #         process = subprocess.Popen(
    #             ["git", "--git-dir", str(repo_path), "archive",
    #             "--format=zip", branch],
    #             stdout=subprocess.PIPE,
    #             stderr=subprocess.PIPE
    #         )
            
    #         # upload_fileobj automatically handles multipart for large streams
    #         self.s3_client.upload_fileobj(
    #             process.stdout,
    #             self.bucket_name,
    #             s3_key,
    #             ExtraArgs={
    #                 'ContentType': 'application/zip',
    #                 'Metadata': {
    #                     'model_id': model_id,
    #                     'package_id': package_id
    #                 }
    #             }
    #         )
            
    #         _, stderr = process.communicate()
            
    #         if process.returncode != 0:
    #             raise RuntimeError(f"git archive failed: {stderr.decode()}")
            
    #         s3_uri = f"s3://{self.bucket_name}/{s3_key}"
    #         self.logger.info(f"Upload complete: {s3_uri}")
    #         return s3_uri