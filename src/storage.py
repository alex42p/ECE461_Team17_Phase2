"""
Simple storage system for MVP.
Stores package metadata in JSON files.
"""

import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

class PackageStorage:
    """Simple file-based storage for packages."""
    
    def __init__(self, storage_dir: str = "package_storage"):
        """Initialize storage directory."""
        self.storage_dir = Path(storage_dir)
        self.metadata_dir = self.storage_dir / "metadata"
        
        # Create directories if they don't exist
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_package_id(self, name: str, version: str) -> str:
        """Generate unique package ID."""
        # Format: name-version-hash
        unique_str = f"{name}-{version}-{datetime.utcnow().isoformat()}"
        hash_suffix = hashlib.md5(unique_str.encode()).hexdigest()[:8]
        return f"{name}-{version}-{hash_suffix}"
    
    def save_package(
        self, 
        name: str,
        version: str,
        url: Optional[str] = None,
        scores: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Save a package with metadata.
        
        Returns:
            Package info including ID and metadata
        """
        # Generate package ID
        package_id = self.generate_package_id(name, version)
        
        # Prepare package metadata
        package_data = {
            "id": package_id,
            "name": name,
            "version": version,
            "url": url,
            "scores": scores or {},
            "created_at": datetime.utcnow().isoformat()
        }
        
        # Save metadata
        metadata_file = self.metadata_dir / f"{package_id}.json"
        with open(metadata_file, "w") as f:
            json.dump(package_data, f, indent=2)
        
        return package_data
    
    def get_package(self, package_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve package by ID.
        
        Returns:
            Package data or None if not found
        """
        metadata_file = self.metadata_dir / f"{package_id}.json"
        
        if not metadata_file.exists():
            return None
        
        with open(metadata_file, "r") as f:
            return json.load(f)
    
    def search_by_regex(self, regex_pattern: str) -> list[Dict[str, Any]]:
        """
        Search packages by regex pattern on name.
        
        Args:
            regex_pattern: Regular expression to match against package names
        
        Returns:
            List of matching packages, sorted by net score (descending)
        """
        import re
        
        try:
            pattern = re.compile(regex_pattern, re.IGNORECASE)
        except re.error as e:
            raise ValueError(f"Invalid regex pattern: {e}")
        
        results = []
        
        # Scan all package metadata files
        for metadata_file in self.metadata_dir.glob("*.json"):
            try:
                with open(metadata_file, "r") as f:
                    package_data = json.load(f)
                
                # Check if name matches pattern
                if pattern.search(package_data.get("name", "")):
                    results.append(package_data)
                    
            except Exception as e:
                print(f"Warning: Error reading {metadata_file}: {e}")
                continue
        
        # Sort by net score (highest first)
        results.sort(
            key=lambda x: x.get("scores", {}).get("net_score", {}).get("value", 0),
            reverse=True
        )
        
        return results

