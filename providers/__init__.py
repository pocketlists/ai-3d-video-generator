"""
Provider abstraction layer — pluggable interfaces for all external services.

Each provider type has a base interface and concrete implementations.
Providers can be swapped via configuration without rewriting the pipeline.

Provider types:
- LLMProvider: AI planning (Gemini, OpenAI, template fallback)
- ThreeDAssetProvider: 3D model generation/retrieval
- TTSProvider: Text-to-speech (Google free, ElevenLabs, espeak)
- MusicProvider: Background music generation
- SFXProvider: Sound effect generation
- LipSyncProvider: Lip-sync analysis from audio
"""
from providers.llm_provider import LLMProvider, GeminiProvider, OpenAIProvider, TemplateProvider
from providers.asset_provider import ThreeDAssetProvider, ConfiguredAssetProvider, CachedAsset
from providers.tts_provider import TTSProvider, GoogleTTSProvider, GTTSProvider, EspeakProvider
from providers.audio_provider import MusicProvider, ProceduralMusicProvider, SFXProvider, ProceduralSFXProvider
from providers.lip_sync_provider import LipSyncProvider, BasicLipSyncProvider

__all__ = [
    "LLMProvider", "GeminiProvider", "OpenAIProvider", "TemplateProvider",
    "ThreeDAssetProvider", "ConfiguredAssetProvider", "CachedAsset",
    "TTSProvider", "GoogleTTSProvider", "GTTSProvider", "EspeakProvider",
    "MusicProvider", "ProceduralMusicProvider",
    "SFXProvider", "ProceduralSFXProvider",
    "LipSyncProvider", "BasicLipSyncProvider",
]
