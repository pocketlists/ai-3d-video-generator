"""Tests for provider abstraction layer."""
import os
import pytest
from unittest.mock import patch, MagicMock

from providers.llm_provider import LLMProvider, GeminiProvider, OpenAIProvider, TemplateProvider, get_llm_provider
from providers.asset_provider import ThreeDAssetProvider, ConfiguredAssetProvider, CachedAsset
from providers.tts_provider import TTSProvider, GoogleTTSProvider, EspeakProvider, get_tts_provider
from providers.audio_provider import MusicProvider, ProceduralMusicProvider, SFXProvider, ProceduralSFXProvider
from providers.lip_sync_provider import LipSyncProvider, BasicLipSyncProvider


def test_template_provider_always_available():
    provider = TemplateProvider({})
    assert provider.is_available()


def test_template_provider_generates_plan():
    provider = TemplateProvider({})
    plan = provider.generate_plan("test prompt")
    assert plan["prompt"] == "test prompt"
    assert plan["ai_generated"] == False
    assert "scenes" in plan
    assert len(plan["scenes"]) == 3


def test_gemini_provider_not_available_without_key():
    os.environ.pop("GEMINI_API_KEY", None)
    provider = GeminiProvider({})
    assert not provider.is_available()


def test_gemini_provider_available_with_key():
    provider = GeminiProvider({"gemini_api_key": "test_key"})
    assert provider.is_available()


def test_openai_provider_not_available_without_key():
    os.environ.pop("OPENAI_API_KEY", None)
    provider = OpenAIProvider({})
    assert not provider.is_available()


def test_get_llm_provider_defaults_to_template():
    provider = get_llm_provider({})
    assert isinstance(provider, TemplateProvider)


def test_get_llm_provider_gemini():
    provider = get_llm_provider({"llm_provider": "gemini", "gemini_api_key": "test"})
    assert isinstance(provider, GeminiProvider)


def test_asset_provider_caching(tmp_path):
    provider = ConfiguredAssetProvider({"asset_cache_dir": str(tmp_path / "assets")})
    assert provider.cache_dir.exists()
    assert (provider.cache_dir / "characters").exists()
    assert (provider.cache_dir / "metadata").exists()


def test_cached_asset_dataclass():
    asset = CachedAsset(
        asset_id="abc123", name="hero", prompt="test",
        provider="api", file_path="/tmp/hero.glb", format="glb"
    )
    d = asset.to_dict()
    assert d["asset_id"] == "abc123"
    assert d["format"] == "glb"


def test_tts_provider_cache_key():
    provider = GoogleTTSProvider({"artifact_dir": "/tmp/test"})
    key1 = provider.get_cache_key("hello", "en")
    key2 = provider.get_cache_key("hello", "en")
    key3 = provider.get_cache_key("hello", "hi")
    assert key1 == key2
    assert key1 != key3


def test_procedural_music_provider_available():
    provider = ProceduralMusicProvider({})
    assert provider.is_available()


def test_procedural_sfx_provider_available():
    provider = ProceduralSFXProvider({})
    assert provider.is_available()


def test_basic_lip_sync_available():
    provider = BasicLipSyncProvider({})
    assert provider.is_available()
