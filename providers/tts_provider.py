"""
TTS Provider — text-to-speech with Google free TTS as primary.

Supports:
- GoogleTTSProvider: Google TTS via gTTS library (free, supports Hindi/English)
- GTTSProvider: Alias for GoogleTTSProvider
- EspeakProvider: eSpeak fallback (offline, lower quality)

Configuration:
- TTS_PROVIDER=google (default)
- TTS_MODE=free (default, uses gTTS)

Features:
- Hindi and Hinglish support
- English support
- Long narration chunking
- Audio merging
- Caching
"""
import hashlib
import os
import subprocess
import tempfile
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from utils.retry import retry
from utils.logger import PipelineLogger


class TTSError(Exception):
    pass


class TTSProvider(ABC):
    """Abstract base for TTS providers."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = PipelineLogger("tts_provider")
        self.cache_dir = os.path.join(
            config.get("artifact_dir", "/tmp/pipeline_artifacts"), "tts_cache"
        )
        os.makedirs(self.cache_dir, exist_ok=True)

    @abstractmethod
    def synthesize(self, text: str, language: str = "en", voice: str = "") -> Optional[str]:
        """Convert text to speech audio file. Returns file path or None."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        ...

    def get_cache_key(self, text: str, language: str) -> str:
        return hashlib.md5(f"{language}_{text}".encode()).hexdigest()

    def get_cached(self, text: str, language: str) -> Optional[str]:
        key = self.get_cache_key(text, language)
        path = os.path.join(self.cache_dir, f"{key}.mp3")
        if os.path.exists(path):
            return path
        return None

    def save_cached(self, text: str, language: str, file_path: str) -> str:
        key = self.get_cache_key(text, language)
        cached_path = os.path.join(self.cache_dir, f"{key}.mp3")
        if file_path != cached_path:
            import shutil
            shutil.copy2(file_path, cached_path)
        return cached_path

    def synthesize_long(self, text: str, language: str = "en", chunk_size: int = 500) -> List[str]:
        """Handle long narration by chunking and merging."""
        if len(text) <= chunk_size:
            result = self.synthesize(text, language)
            return [result] if result else []

        chunks = self._split_text(text, chunk_size)
        audio_files = []
        for i, chunk in enumerate(chunks):
            self.logger.info(f"TTS chunk {i+1}/{len(chunks)}: {len(chunk)} chars")
            result = self.synthesize(chunk, language)
            if result:
                audio_files.append(result)
        return audio_files

    def _split_text(self, text: str, chunk_size: int) -> List[str]:
        """Split text at sentence boundaries."""
        import re
        sentences = re.split(r'(?<=[.!?])\s+', text)
        chunks = []
        current = ""
        for sentence in sentences:
            if len(current) + len(sentence) <= chunk_size:
                current += " " + sentence if current else sentence
            else:
                if current:
                    chunks.append(current.strip())
                current = sentence
        if current:
            chunks.append(current.strip())
        return chunks


class GoogleTTSProvider(TTSProvider):
    """Google TTS via gTTS library — free, supports Hindi and English."""

    def is_available(self) -> bool:
        try:
            from gtts import gTTS
            return True
        except ImportError:
            return False

    @retry(max_attempts=3, initial_delay=2.0, retryable_messages=["timeout", "429", "503"])
    def synthesize(self, text: str, language: str = "en", voice: str = "") -> Optional[str]:
        cached = self.get_cached(text, language)
        if cached:
            self.logger.info(f"TTS cache hit: {language}, {len(text)} chars")
            return cached

        try:
            from gtts import gTTS
        except ImportError:
            self.logger.error("gTTS not installed")
            return None

        # Map language codes
        lang_map = {"hindi": "hi", "hinglish": "hi", "english": "en", "en": "en", "hi": "hi"}
        gtts_lang = lang_map.get(language.lower(), "en")

        try:
            output = os.path.join(self.cache_dir, f"tts_{int(time.time()*1000)}.mp3")
            tts = gTTS(text=text, lang=gtts_lang, slow=False, tld="com")
            tts.save(output)
            cached_path = self.save_cached(text, language, output)
            if output != cached_path:
                os.unlink(output)
            self.logger.info(f"TTS generated: {cached_path} ({gtts_lang}, {len(text)} chars)")
            return cached_path
        except Exception as e:
            self.logger.error(f"gTTS failed: {e}")
            return None


class GTTSProvider(GoogleTTSProvider):
    """Alias for GoogleTTSProvider."""
    pass


class EspeakProvider(TTSProvider):
    """eSpeak fallback TTS — offline, lower quality."""

    def is_available(self) -> bool:
        try:
            result = subprocess.run(["espeak", "--version"], capture_output=True, timeout=5)
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def synthesize(self, text: str, language: str = "en", voice: str = "") -> Optional[str]:
        cached = self.get_cached(text, language)
        if cached:
            return cached

        lang_map = {"hindi": "hi", "hinglish": "hi", "english": "en"}
        espeak_lang = lang_map.get(language.lower(), "en")

        output = os.path.join(self.cache_dir, f"tts_{int(time.time()*1000)}.wav")
        try:
            result = subprocess.run(
                ["espeak", "-v", espeak_lang, "-w", output, text],
                capture_output=True, timeout=30
            )
            if result.returncode == 0 and os.path.exists(output):
                return output
            return None
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            self.logger.error(f"espeak failed: {e}")
            return None


def get_tts_provider(config: Dict[str, Any]) -> TTSProvider:
    """Factory: select TTS provider based on configuration.

    TTS_PROVIDER options:
    - google_cloud → Google Cloud Text-to-Speech (production, needs credentials)
    - google / gtts → gTTS (free, rate-limited — NOT Google Cloud TTS)
    - espeak → local espeak fallback
    """
    provider_name = config.get("tts_provider", "gtts")
    if provider_name == "google_cloud":
        from providers.google_cloud_tts import GoogleCloudTTSProvider
        provider = GoogleCloudTTSProvider(config)
        if provider.is_available():
            return provider
        # DO NOT silently fall back to gTTS when Cloud TTS was explicitly requested
        raise RuntimeError(
            "TTS_PROVIDER=google_cloud but Google Cloud TTS credentials not configured "
            "(GOOGLE_TTS_API_KEY or GOOGLE_APPLICATION_CREDENTIALS). "
            "Set credentials or use TTS_PROVIDER=gtts for the free tier."
        )
    if provider_name == "gtts":
        provider = GoogleTTSProvider(config)
        if provider.is_available():
            return provider
    if provider_name == "google":
        provider = GoogleTTSProvider(config)
        if provider.is_available():
            return provider
    if provider_name == "espeak":
        provider = EspeakProvider(config)
        if provider.is_available():
            return provider
    # Try espeak as fallback
    espeak = EspeakProvider(config)
    if espeak.is_available():
        return espeak
    # Last resort: Google TTS even if gTTS not installed (will fail gracefully)
    return GoogleTTSProvider(config)
