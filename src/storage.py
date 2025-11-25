"""
Simple storage system for MVP.
Stores package metadata in JSON files.
"""

import json
import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any

class PackageStorage:
    """Simple file-based storage for packages."""
    
    def __init__(self, storage_dir: str = "package_storage"):
        """Initialize storage directory."""
        self.__name__ = "PackageStorage"
        self.storage_dir = Path(storage_dir)
        self.metadata_dir = self.storage_dir / "metadata"
        
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
        scores: Optional[Dict[str, Any]] = None
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
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        # Save metadata
        metadata_file = self.metadata_dir / f"{package_id}.json"
        try:
            with open(metadata_file, "w") as f:
                json.dump(package_data, f, indent=2)
            self.logger.info("save_package: wrote metadata %s", metadata_file.name)
        except Exception as e:
            self.logger.exception("save_package: failed to write metadata %s: %s", metadata_file.name, e)

        return package_data
    
    def get_package(self, package_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve package by ID.
        
        Returns:
            Package data or None if not found
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
                self.logger.debug("get_package: loaded %s", metadata_file.name)
                return data
        except Exception as e:
            self.logger.exception("get_package: failed to read %s: %s", metadata_file.name, e)
            return None
    
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

