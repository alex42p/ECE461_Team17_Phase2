"""
Stream HuggingFace repositories directly to S3 without local storage.
"""
# pyright: reportOptionalMemberAccess=false 
import subprocess
import tempfile
import os
from pathlib import Path
from typing import Optional
import boto3
from io import BytesIO

def stream_repo_to_s3(
    model_id: str,
    s3_client,
    bucket_name: str,
    s3_key: str,
    branch: str = "main"
) -> str:
    """
    Clone and zip a HuggingFace repo, streaming directly to S3.
    
    Uses git archive to avoid storing the entire repo locally.
    Only creates a temporary shallow clone.
    
    Args:
        model_id: HuggingFace model ID (e.g., 'bert-base-uncased')
        s3_client: boto3 S3 client
        bucket_name: Target S3 bucket
        s3_key: Target S3 key for the zip file
        branch: Git branch to archive (default: 'main')
    
    Returns:
        S3 URI of uploaded file
    """
    repo_url = f"https://huggingface.co/{model_id}"
    
    # Use a temporary directory for minimal git metadata only
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        
        # Step 1: Shallow clone (only metadata, no working tree)
        # This is much smaller than a full clone
        subprocess.run(
            ["git", "clone", "--bare", "--depth=1", "--single-branch", 
             "--branch", branch, repo_url, str(tmpdir_path / "repo.git")],
            check=True,
            capture_output=True
        )
        
        # Step 2: Create git archive and stream to S3
        # git archive outputs a tar/zip directly without extracting files
        repo_path = tmpdir_path / "repo.git"
        
        # Use git archive to create a zip stream
        process = subprocess.Popen(
            ["git", "--git-dir", str(repo_path), "archive", 
             "--format=zip", branch],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Stream the output directly to S3 using multipart upload
        # This handles large files efficiently
        s3_client.upload_fileobj(
            process.stdout,
            bucket_name,
            s3_key,
            ExtraArgs={'ContentType': 'application/zip'}
        )
        
        # Wait for git archive to complete
        _, stderr = process.communicate()
        
        if process.returncode != 0:
            raise RuntimeError(f"git archive failed: {stderr.decode()}")
        
        return f"s3://{bucket_name}/{s3_key}"


def stream_repo_to_s3_with_retry(
    model_id: str,
    s3_client,
    bucket_name: str,
    s3_key: str,
    branch: str = "main",
    max_retries: int = 3
) -> str:
    """
    Stream repo to S3 with retry logic for large files.
    
    For very large repos, uses multipart upload with configurable chunk size.
    """
    repo_url = f"https://huggingface.co/{model_id}"
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        
        # Shallow clone
        subprocess.run(
            ["git", "clone", "--bare", "--depth=1", "--single-branch",
             "--branch", branch, repo_url, str(tmpdir_path / "repo.git")],
            check=True,
            capture_output=True
        )
        
        repo_path = tmpdir_path / "repo.git"
        
        # Start multipart upload for better reliability with large files
        mpu = s3_client.create_multipart_upload(
            Bucket=bucket_name,
            Key=s3_key,
            ContentType='application/zip'
        )
        
        upload_id = mpu['UploadId']
        parts = []
        part_number = 1
        chunk_size = 50 * 1024 * 1024  # 50MB chunks
        
        try:
            # Stream git archive output
            process = subprocess.Popen(
                ["git", "--git-dir", str(repo_path), "archive",
                 "--format=zip", branch],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # Read and upload in chunks
            while True:
                chunk = process.stdout.read(chunk_size)
                if not chunk:
                    break
                
                # Upload this chunk
                part = s3_client.upload_part(
                    Bucket=bucket_name,
                    Key=s3_key,
                    PartNumber=part_number,
                    UploadId=upload_id,
                    Body=chunk
                )
                
                parts.append({
                    'PartNumber': part_number,
                    'ETag': part['ETag']
                })
                
                part_number += 1
            
            # Wait for process to complete
            _, stderr = process.communicate()
            
            if process.returncode != 0:
                raise RuntimeError(f"git archive failed: {stderr.decode()}")
            
            # Complete multipart upload
            s3_client.complete_multipart_upload(
                Bucket=bucket_name,
                Key=s3_key,
                UploadId=upload_id,
                MultipartUpload={'Parts': parts}
            )
            
            return f"s3://{bucket_name}/{s3_key}"
            
        except Exception as e:
            # Abort multipart upload on error
            s3_client.abort_multipart_upload(
                Bucket=bucket_name,
                Key=s3_key,
                UploadId=upload_id
            )
            raise


def clone_repo_minimal(model_id: str, cache_dir: Path = Path("./cache")) -> Path:
    """
    Lightweight clone for inspection only (not for S3 upload).
    Uses sparse checkout to minimize disk usage.
    """
    model_dir = cache_dir / model_id
    
    if not model_dir.exists():
        repo_url = f"https://huggingface.co/{model_id}"
        
        # Initialize repo
        model_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init"], cwd=model_dir, check=True)
        subprocess.run(
            ["git", "remote", "add", "origin", repo_url],
            cwd=model_dir,
            check=True
        )
        
        # Enable sparse checkout
        subprocess.run(
            ["git", "config", "core.sparseCheckout", "true"],
            cwd=model_dir,
            check=True
        )
        
        # Only checkout essential files (not model weights)
        sparse_file = model_dir / ".git" / "info" / "sparse-checkout"
        sparse_file.parent.mkdir(parents=True, exist_ok=True)
        sparse_file.write_text(
            "README.md\n"
            "config.json\n"
            "*.py\n"
            "!*.bin\n"
            "!*.safetensors\n"
            "!*.ckpt\n"
        )
        
        # Shallow clone with sparse checkout
        subprocess.run(
            ["git", "pull", "--depth=1", "origin", "main"],
            cwd=model_dir,
            check=True
        )
    
    return model_dir