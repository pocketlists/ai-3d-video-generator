"""
3D Asset Provider — generates and retrieves real 3D models via configurable API.

Supports:
- GLB/GLTF format (primary)
- FBX/OBJ (if API provides)
- Asset caching with stable IDs
- Metadata tracking
- Validation of downloaded assets

Configuration:
- THREE_D_ASSET_API_KEY: API key for the 3D asset service
- THREE_D_ASSET_API_URL: Base URL for the API
- ASSET_CACHE_DIR: Local cache directory (default: assets/)

Asset cache structure:
  assets/
    characters/  — character GLB files
    environments/ — environment GLB files
    props/       — prop GLB files
    metadata/    — JSON metadata for each asset
"""
import hashlib
import json
import os
import time
import urllib.request
import urllib.error
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.retry import retry
from utils.logger import PipelineLogger


@dataclass
class CachedAsset:
    """A cached 3D asset with metadata."""
    asset_id: str
    name: str
    prompt: str
    provider: str
    file_path: str
    format: str  # glb, gltf, fbx, obj
    file_size: int = 0
    file_hash: str = ""
    created_at: float = 0.0
    generation_time: float = 0.0
    validation_status: str = "pending"  # pending, valid, invalid
    rig_status: str = "unknown"  # unknown, rigged, static
    texture_status: str = "unknown"  # unknown, textured, untextured
    mesh_count: int = 0
    material_count: int = 0
    polygon_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "asset_id": self.asset_id, "name": self.name, "prompt": self.prompt,
            "provider": self.provider, "file_path": self.file_path, "format": self.format,
            "file_size": self.file_size, "file_hash": self.file_hash,
            "created_at": self.created_at, "generation_time": self.generation_time,
            "validation_status": self.validation_status, "rig_status": self.rig_status,
            "texture_status": self.texture_status, "mesh_count": self.mesh_count,
            "material_count": self.material_count, "polygon_count": self.polygon_count,
            "metadata": self.metadata,
        }


class ThreeDAssetProvider(ABC):
    """Abstract base for 3D asset providers."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = PipelineLogger("asset_provider")
        self.cache_dir = Path(config.get("asset_cache_dir", "assets"))
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        for subdir in ["characters", "environments", "props", "metadata"]:
            (self.cache_dir / subdir).mkdir(exist_ok=True)

    @abstractmethod
    def is_available(self) -> bool:
        ...

    @abstractmethod
    def generate_asset(self, prompt: str, asset_type: str, name: str) -> Optional[CachedAsset]:
        ...

    def get_or_create(self, prompt: str, asset_type: str, name: str) -> Optional[CachedAsset]:
        """Get cached asset or generate new one. Never regenerates the same asset."""
        cached = self._find_cached(name, asset_type)
        if cached:
            self.logger.info(f"Reusing cached asset: {name} ({asset_type})")
            return cached
        return self.generate_asset(prompt, asset_type, name)

    def _find_cached(self, name: str, asset_type: str) -> Optional[CachedAsset]:
        """Find a cached asset by name and type."""
        meta_path = self.cache_dir / "metadata" / f"{asset_type}_{name}.json"
        if meta_path.exists():
            with open(meta_path) as f:
                data = json.load(f)
            asset = CachedAsset(**data)
            if Path(asset.file_path).exists():
                return asset
        return None

    def _save_asset(self, asset: CachedAsset) -> None:
        """Save asset metadata to cache."""
        meta_path = self.cache_dir / "metadata" / f"{asset.metadata.get('asset_type', 'misc')}_{asset.name}.json"
        asset.file_size = os.path.getsize(asset.file_path) if os.path.exists(asset.file_path) else 0
        with open(meta_path, "w") as f:
            json.dump(asset.to_dict(), f, indent=2)

    def _compute_hash(self, file_path: str) -> str:
        """Compute SHA256 hash of a file."""
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def _generate_asset_id(self, prompt: str, name: str) -> str:
        """Generate a stable asset ID from prompt and name."""
        return hashlib.md5(f"{name}_{prompt}".encode()).hexdigest()[:12]


class ConfiguredAssetProvider(ThreeDAssetProvider):
    """3D asset provider using a configurable API endpoint."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = config.get("three_d_asset_api_key") or os.environ.get("THREE_D_ASSET_API_KEY", "")
        self.api_url = config.get("three_d_asset_api_url") or os.environ.get("THREE_D_ASSET_API_URL", "")
        self.timeout = int(config.get("asset_api_timeout", 300))

    def is_available(self) -> bool:
        return bool(self.api_key and self.api_url)

    @retry(max_attempts=2, initial_delay=5.0, backoff_factor=2.0,
           retryable_messages=["timeout", "429", "503", "rate_limit"])
    def generate_asset(self, prompt: str, asset_type: str, name: str) -> Optional[CachedAsset]:
        if not self.is_available():
            self.logger.warning(f"3D asset API not configured, cannot generate: {name}")
            return None

        self.logger.info(f"Generating 3D asset via API: {name} ({asset_type})")
        start_time = time.time()

        try:
            asset_data = self._call_api(prompt, asset_type)
            if not asset_data:
                return None

            file_format = asset_data.get("format", "glb")
            file_content = asset_data.get("content", b"")
            download_url = asset_data.get("download_url", "")

            if download_url and not file_content:
                file_content = self._download_file(download_url)

            if not file_content:
                self.logger.error(f"No asset data received for: {name}")
                return None

            asset_id = self._generate_asset_id(prompt, name)
            file_path = self.cache_dir / asset_type / f"{name}.{file_format}"
            with open(file_path, "wb") as f:
                f.write(file_content)

            asset = CachedAsset(
                asset_id=asset_id, name=name, prompt=prompt,
                provider="configured_api", file_path=str(file_path),
                format=file_format, created_at=time.time(),
                generation_time=time.time() - start_time,
                file_hash=self._compute_hash(str(file_path)),
                validation_status="pending",
                metadata={"asset_type": asset_type, "download_url": download_url},
            )

            self._save_asset(asset)
            self.logger.info(f"Asset saved: {file_path} ({len(file_content)} bytes)")
            return asset

        except Exception as e:
            self.logger.error(f"Asset generation failed for {name}: {e}")
            return None

    def _call_api(self, prompt: str, asset_type: str) -> Optional[Dict]:
        """Call the configured 3D asset API."""
        payload = json.dumps({
            "prompt": prompt,
            "type": asset_type,
            "format": "glb",
        }).encode()

        req = urllib.request.Request(self.api_url, data=payload)
        req.add_header("Authorization", f"Bearer {self.api_key}")
        req.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                result = json.loads(resp.read().decode())
            return result
        except urllib.error.HTTPError as e:
            error_body = e.read().decode() if e.fp else str(e)
            self.logger.error(f"Asset API HTTP {e.code}: {error_body}")
            return None
        except urllib.error.URLError as e:
            self.logger.error(f"Asset API URL error: {e}")
            return None

    def _download_file(self, url: str) -> bytes:
        """Download a file from a URL."""
        try:
            with urllib.request.urlopen(url, timeout=self.timeout) as resp:
                return resp.read()
        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            self.logger.error(f"Download failed: {url} — {e}")
            return b""


def get_asset_provider(config: Dict[str, Any]) -> ThreeDAssetProvider:
    """Factory: select 3D asset provider based on configuration."""
    return ConfiguredAssetProvider(config)
