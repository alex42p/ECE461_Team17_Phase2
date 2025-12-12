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
from typing import Optional, Dict, Any, List

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
        # Always resolve to absolute path to avoid working directory issues
        # Convert to Path if it's a string, then resolve to absolute
        if isinstance(storage_dir, str):
            self.storage_dir = Path(storage_dir).resolve()
        else:
            self.storage_dir = Path(storage_dir).resolve()
        self.metadata_dir = (self.storage_dir / "metadata").resolve()
        self.s3_client = boto3.client(
            's3', 
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key,
            region_name=aws_region,
        )
        self.bucket_name = bucket_name
        
        # Create directories if they don't exist
        self.metadata_dir.mkdir(parents=True, exist_ok=True)

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
            fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
            fh.setFormatter(fmt)
            self.logger.addHandler(fh)
        self.logger.info("Initialized PackageStorage")
    
    
    def generate_package_id(self, name: str, version: str) -> str:
        """Generate unique package ID."""
        # Format: name-version-hash
        # sanitize name to avoid path separators in filenames
        safe_name = name.replace('/', '_').replace('\\', '_')
        unique_str = f"{safe_name}-{version}-{datetime.now(timezone.utc).isoformat()}"
        hash_suffix = hashlib.md5(unique_str.encode()).hexdigest()[:8]
        pkg_id = f"{safe_name}-{version}-{hash_suffix}"
        try:
            self.logger.debug("generate_package_id: name=%s safe_name=%s version=%s -> %s", name, safe_name, version, pkg_id)
        except Exception:
            pass
        return pkg_id
    
    def save_package(
        self, 
        name: str,
        version: str,
        url: Optional[str] = None,
        scores: Optional[Dict[str, Any]] = None,
        file_path: Optional[str] = None,
        artifact_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Save a package with metadata.
        
        Returns:
            Package info including ID and metadata
        """
        self.logger.debug("save_package called: name=%s version=%s url=%s", name, version, url)

        # Sanitize name for filesystem use and check for existing package
        safe_name = name.replace('/', '_').replace('\\', '_')
        # If a package with same safe_name and version already exists, return it
        existing = list(self.metadata_dir.glob(f"{safe_name}-{version}-*.json"))
        if existing:
            try:
                self.logger.info("save_package: found existing metadata file %s for %s", existing[0].name, name)
                with open(existing[0], "r") as f:
                    data = json.load(f)
                    return data
            except Exception as e:
                self.logger.exception("save_package: failed to read existing metadata %s: %s", existing[0].name, e)
                # If reading fails, continue and create a new one
                pass

        # Generate package ID
        package_id = self.generate_package_id(name, version)
        
        # Prepare package metadata
        package_data = {
            "id": package_id,
            "name": name,
            "version": version,
            "url": url,
            "scores": scores or {},
            "artifact_type": artifact_type or "model",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        # If a file_path is provided, upload the file to S3 and update metadata
        if file_path:
            try:
                # Use a namespaced key to avoid collisions
                base_name = os.path.basename(file_path)
                s3_key = f"packages/{package_id}/{base_name}"
                s3_uri = self.upload_file_to_s3(file_path, s3_key)
                # add s3 metadata and update URL to point to S3 URI
                package_data.setdefault('s3', {})
                package_data['s3']['bucket'] = self.bucket_name # type: ignore
                package_data['s3']['key'] = s3_key # type: ignore
                package_data['s3']['uri'] = s3_uri # type: ignore
                package_data['url'] = s3_uri # type: ignore
                self.logger.info("save_package: uploaded file %s to S3 as %s", file_path, s3_uri)
            except Exception:
                # Log and continue — metadata will still be saved locally
                self.logger.exception("save_package: failed to upload file %s to S3", file_path)
        
        # Save metadata
        metadata_file = self.metadata_dir / f"{package_id}.json"
        try:
            with open(metadata_file, "w") as f:
                json.dump(package_data, f, indent=2)
            self.logger.info("save_package: wrote metadata %s", metadata_file.name)
        except Exception as e:
            self.logger.exception("save_package: failed to write metadata %s: %s", metadata_file.name, e)

        return package_data

    def upload_file_to_s3(self, file_path: str, s3_key: str) -> str:
        """
        Upload a local file to S3 and return the S3 URI (s3://bucket/key).
        """
        if not self.bucket_name:
            raise ValueError("S3 bucket name is not configured (S3_BUCKET_NAME).")

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

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
    
    def search_by_regex(self, regex_pattern: str) -> List[Dict[str, Any]]:
        """
        Search packages by regex pattern on name.
        
        Args:
            regex_pattern: Regular expression to match against package names
        
        Returns:
            List of matching packages, sorted by net score (descending)
        """
        import re

        try:
            self.logger.debug("search_by_regex: pattern=%s", regex_pattern)
        except Exception:
            pass

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

        self.logger.debug("search_by_regex: found %d matches for pattern %s", len(results), regex_pattern)
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

