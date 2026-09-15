"""
Asset router — routes asset requests across multiple providers.

Routing order:
1. CACHE (content-hash based local cache)
2. OBJAVERSE (dataset retrieval)
3. EXTERNAL_3D_API (configured provider)
4. PROCEDURAL (fallback — only for smoke tests / explicit fallback)

For PRODUCTION: if quality threshold cannot be met by any provider,
ESCALATE instead of silently using procedural fallback.
"""
import os
from typing import Any, Dict, Optional

from utils.logger import PipelineLogger
from providers.asset_provider import ThreeDAssetProvider, ConfiguredAssetProvider, CachedAsset
from providers.objaverse_provider import ObjaverseProvider


class AssetRouter:
    """Routes asset requests to the best available provider."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = PipelineLogger("asset_router")
        self.quality_threshold = config.get("min_asset_quality_score", 0.6)

        # Initialize providers
        self.objaverse = ObjaverseProvider(config)
        self.external_api = ConfiguredAssetProvider(config)

        # Provider order
        self.routing_order = config.get("asset_routing_order", ["cache", "objaverse", "external_api"])

    def get_or_create(self, prompt: str, asset_type: str, name: str,
                      allow_procedural: bool = False) -> Optional[CachedAsset]:
        """Get asset from cache or create via best available provider."""
        # 1. Check cache first (always)
        for provider in [self.objaverse, self.external_api]:
            cached = provider._find_cached(name, asset_type)
            if cached and os.path.exists(cached.file_path):
                self.logger.info(f"Cache hit: {name} ({asset_type})")
                return cached

        # 2. Try providers in routing order
        providers = {
            "objaverse": self.objaverse,
            "external_api": self.external_api,
        }

        for provider_name in self.routing_order:
            if provider_name == "cache":
                continue  # Already checked above
            provider = providers.get(provider_name)
            if not provider:
                continue

            if not provider.is_available():
                self.logger.info(f"Provider not available: {provider_name}")
                continue

            self.logger.info(f"Trying provider: {provider_name}")
            asset = provider.get_or_create(prompt, asset_type, name)
            if asset:
                self.logger.info(f"Asset created via {provider_name}: {name}")
                return asset

        # 3. No provider succeeded
        if allow_procedural:
            self.logger.warning(f"Using procedural fallback for {name} (explicitly allowed)")
            return None  # Caller handles procedural

        # Production: escalate
        self.logger.error(
            f"No asset provider could create: {name} ({asset_type}) — {prompt[:60]}. "
            f"ESCALTION REQUIRED for production quality."
        )
        return None

    def capabilities(self) -> Dict[str, Dict]:
        """Get capabilities of all providers."""
        return {
            "objaverse": self.objaverse.capabilities() if self.objaverse.is_available() else {"available": False},
            "external_api": {"available": self.external_api.is_available()},
        }
