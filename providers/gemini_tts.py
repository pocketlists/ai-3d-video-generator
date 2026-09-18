"""
Gemini TTS provider — speech generation via the Gemini API (generateContent).

Uses the SAME GEMINI_API_KEY as planning (no extra secret needed).

Supported models (verified against Google's official docs, Sep 2026):
  - gemini-2.5-flash-preview-tts   (fast, low-latency)
  - gemini-2.5-pro-preview-tts      (studio-quality, long-form)
  - gemini-3.1-flash-tts-preview    (newest, supports streaming)

Output: base64 PCM (audio/L16;codec=pcm;rate=24000) → converted to WAV.

Voice: 30 prebuilt voices (Kore, Puck, Zephyr, Aoede, ...), configurable
via GEMINI_TTS_VOICE. Style control via natural-language prefix
(e.g. "Say cheerfully: ..."). Hindi/Hinglish text is supported by the
model itself (language follows the input text).

PROVIDER_DEPENDENT: requires GEMINI_API_KEY; interface verified locally
with mocks, real API not tested in this environment.
"""
import base64
import json
import os
import re
import struct
import tempfile
import urllib.error
import urllib.request
import wave
from typing import Any, Dict, Optional

from providers.tts_provider import TTSProvider
from utils.logger import PipelineLogger
from utils.error_classifier import classify_error

# Official Gemini TTS model IDs (ai.google.dev/gemini-api/docs/models)
SUPPORTED_MODELS = [
    "gemini-2.5-flash-preview-tts",
    "gemini-2.5-pro-preview-tts",
    "gemini-3.1-flash-tts-preview",
]

# 30 official prebuilt voice names
SUPPORTED_VOICES = [
    "Zephyr", "Puck", "Charon", "Kore", "Fenrir", "Leda", "Orus", "Aoede",
    "Callirrhoe", "Autonoe", "Enceladus", "Iapetus", "Umbriel", "Algieba",
    "Despina", "Erinome", "Algenib", "Rasalgethi", "Laomedeia", "Achernar",
    "Alnilam", "Schedar", "Gacrux", "Pulcherrima", "Achird",
    "Zubenelgenubi", "Vindemiatrix", "Sadachbia", "Sadaltager", "Sulafat",
]


class GeminiTTSProvider(TTSProvider):
    """Gemini text-to-speech via the generateContent REST API."""

    API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.logger = PipelineLogger("gemini_tts")
        self.api_key = (
            config.get("gemini_api_key")
            or os.environ.get("GEMINI_API_KEY", "")
        )
        self.model = (
            config.get("gemini_tts_model")
            or os.environ.get("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts")
        )
        if self.model not in SUPPORTED_MODELS:
            self.logger.warning(
                f"GEMINI_TTS_MODEL={self.model} is not in the officially "
                f"supported list {SUPPORTED_MODELS} — attempting anyway"
            )
        self.voice = (
            config.get("gemini_tts_voice")
            or os.environ.get("GEMINI_TTS_VOICE", "Kore")
        )
        if self.voice not in SUPPORTED_VOICES:
            self.logger.warning(
                f"GEMINI_TTS_VOICE={self.voice} is not in the 30 official "
                f"prebuilt voices — attempting anyway"
            )
        # Optional style instruction, e.g. "Say warmly"
        self.style = config.get("gemini_tts_style", "")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def capabilities(self) -> Dict[str, Any]:
        return {
            "ssml": False,
            "multi_language": True,   # language follows input text
            "voice_selection": True,
            "speaking_rate": False,
            "pitch": False,
            "style_control": True,   # natural-language style prompts
            "hindi": True,
            "hinglish": True,        # code-mixed text follows input
        }

    def health_check(self) -> bool:
        return self.is_available()

    def synthesize(self, text: str, language: str = "", voice: str = "") -> Optional[str]:
        """Convert text to speech. Returns WAV file path or None on failure."""
        if not self.is_available():
            self.logger.error(
                "TTS_PROVIDER=gemini_tts but GEMINI_API_KEY is not set. "
                "Gemini TTS uses the same key as planning — set GEMINI_API_KEY "
                "or choose another TTS_PROVIDER."
            )
            return None

        text = (text or "").strip()
        if not text:
            return None

        use_voice = voice or self.voice
        styled = f"{self.style}: {text}" if self.style else text

        payload = {
            "contents": [{"parts": [{"text": styled}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {"voiceName": use_voice}
                    }
                },
            },
        }

        url = f"{self.API_BASE}/{self.model}:generateContent"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.api_key,
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="ignore")[:300]
            except Exception:
                pass
            self.logger.error(
                f"Gemini TTS HTTP {e.code} from model {self.model}: {body}"
            )
            return None
        except (urllib.error.URLError, TimeoutError) as e:
            self.logger.error(f"Gemini TTS network error: {e}")
            return None

        # Extract base64 PCM audio from the response
        try:
            inline = (
                data["candidates"][0]["content"]["parts"][0]["inlineData"]
            )
            audio_b64 = inline["data"]
            mime = inline.get("mimeType", "audio/L16;codec=pcm;rate=24000")
        except (KeyError, IndexError, TypeError):
            self.logger.error(
                "Gemini TTS response contained no audio inlineData "
                f"(response keys: {list(data.keys())})"
            )
            return None

        pcm = base64.b64decode(audio_b64)
        sample_rate = 24000
        m = re.search(r"rate=(\d+)", mime)
        if m:
            sample_rate = int(m.group(1))

        # PCM (L16, mono) → WAV with a proper header
        out_path = os.path.join(
            tempfile.gettempdir(),
            f"gemini_tts_{abs(hash(text)) & 0xffffffff:x}.wav",
        )
        try:
            with wave.open(out_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)  # 16-bit
                wf.setframerate(sample_rate)
                wf.writeframes(pcm)
        except (OSError, wave.Error) as e:
            self.logger.error(f"Gemini TTS failed writing WAV: {e}")
            return None

        self.logger.info(
            f"Gemini TTS: model={self.model} voice={use_voice} "
            f"chars={len(text)} -> {out_path}"
        )
        return out_path
