"""
Google Cloud Text-to-Speech provider — uses the Cloud TTS REST API.

This is SEPARATE from gTTS (the `gtts` package / Google Translate TTS):
- Google Cloud TTS: production-grade, requires credentials, quota/paid
- gTTS: free, rate-limited, NOT Google Cloud TTS

Configuration:
  TTS_PROVIDER=google_cloud  → this provider (no silent gTTS fallback)
  TTS_PROVIDER=gtts           → free gTTS provider
  GOOGLE_TTS_API_KEY          → Cloud TTS REST API key

PROVIDER_DEPENDENT: requires Google Cloud credentials; interface verified
locally with mocks, real API not tested in this environment.
"""
import base64
import json
import os
import re
import tempfile
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from providers.tts_provider import TTSProvider
from utils.logger import PipelineLogger
from utils.error_classifier import classify_error


class GoogleCloudTTSProvider(TTSProvider):
    """Production Google Cloud Text-to-Speech via REST API."""

    API_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.logger = PipelineLogger("google_cloud_tts")
        self.api_key = config.get("google_tts_api_key") or os.environ.get("GOOGLE_TTS_API_KEY", "")
        self.credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
        self.language = config.get("google_tts_language", "en-US")
        self.voice_name = config.get("google_tts_voice", "en-US-Standard-A")
        self.speaking_rate = float(config.get("tts_speaking_rate", 1.0))
        self.pitch = float(config.get("tts_pitch", 0.0))

    def is_available(self) -> bool:
        return bool(self.api_key) or bool(self.credentials_path)

    def capabilities(self) -> Dict[str, Any]:
        return {
            "ssml": True, "multi_language": True, "voice_selection": True,
            "speaking_rate": True, "pitch": True, "hindi": True,
            "hinglish": True,  # via en-IN / hi-IN voices with code-mixed text
        }

    def health_check(self) -> bool:
        return self.is_available()

    def synthesize(self, text: str, language: str = "", voice: str = "") -> Optional[str]:
        """Convert text to speech. Returns audio file path or None on failure."""
        if not self.is_available():
            self.logger.error(
                "Google Cloud TTS not configured — set GOOGLE_TTS_API_KEY "
                "or GOOGLE_APPLICATION_CREDENTIALS"
            )
            return None

        lang = language or self.language
        vname = voice or self.voice_name

        # Cache check
        cached = self.get_cached(text, lang)
        if cached:
            return cached

        # Chunk long text (Cloud TTS limit: 5000 bytes per request)
        chunks = self._chunk_text(text, max_bytes=4500)
        audio_files = []
        for i, chunk in enumerate(chunks):
            out = self._synthesize_chunk(chunk, lang, vname, i)
            if out is None:
                return None
            audio_files.append(out)

        final_path = audio_files[0] if len(audio_files) == 1 else self._merge_mp3(audio_files)

        # Store in cache
        key = self.get_cache_key(text, lang)
        cache_path = os.path.join(self.cache_dir, f"{key}.mp3")
        if final_path != cache_path:
            with open(final_path, "rb") as src, open(cache_path, "wb") as dst:
                dst.write(src.read())
        self.logger.info(f"Cloud TTS generated: {cache_path} ({lang}, {len(chunks)} chunk(s))")
        return cache_path

    def _synthesize_chunk(self, chunk: str, lang: str, voice: str, index: int) -> Optional[str]:
        payload = json.dumps({
            "input": {"text": chunk},
            "voice": {"languageCode": lang, "name": voice},
            "audioConfig": {
                "audioEncoding": "MP3",
                "speakingRate": self.speaking_rate,
                "pitch": self.pitch,
            },
        }).encode()

        url = self.API_URL + (f"?key={self.api_key}" if self.api_key else "")
        req = urllib.request.Request(url, data=payload)
        req.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode())
            audio_b64 = result.get("audioContent", "")
            if not audio_b64:
                self.logger.error(f"Cloud TTS returned empty audio for chunk {index}")
                return None
            audio_bytes = base64.b64decode(audio_b64)
            tmp = tempfile.NamedTemporaryFile(
                suffix=f"_gctts_{index}.mp3", delete=False, dir=self.cache_dir
            )
            tmp.write(audio_bytes)
            tmp.close()
            return tmp.name
        except urllib.error.HTTPError as e:
            body = e.read().decode() if e.fp else str(e)
            etype = classify_error(body)
            self.logger.error(f"Cloud TTS HTTP {e.code} ({etype}): {body[:200]}")
            return None
        except urllib.error.URLError as e:
            self.logger.error(f"Cloud TTS network error: {e}")
            return None

    @staticmethod
    def _chunk_text(text: str, max_bytes: int = 4500) -> list:
        """Split long text into chunks within the API byte limit (sentence-safe)."""
        if len(text.encode("utf-8")) <= max_bytes:
            return [text]
        chunks, current = [], ""
        for sent in re.split(r"(?<=[.!?।])\s+", text):  # includes Hindi danda
            candidate = (current + " " + sent).strip() if current else sent
            if len(candidate.encode("utf-8")) > max_bytes:
                if current:
                    chunks.append(current)
                current = sent
            else:
                current = candidate
        if current:
            chunks.append(current)
        return chunks

    def _merge_mp3(self, files: list) -> str:
        """Concatenate MP3 chunks (no re-encode)."""
        out = tempfile.NamedTemporaryFile(
            suffix="_merged.mp3", delete=False, dir=self.cache_dir
        )
        for f in files:
            with open(f, "rb") as src:
                out.write(src.read())
        out.close()
        return out.name
