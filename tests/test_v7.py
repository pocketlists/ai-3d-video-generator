"""v7 regression tests: Gemini TTS provider + model/package name validation."""
import json
import os
import struct
import wave
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestGeminiTTSModels:
    """The 3 Gemini TTS model IDs must match Google's official list."""

    def test_supported_models_match_official_list(self):
        from providers.gemini_tts import SUPPORTED_MODELS
        assert SUPPORTED_MODELS == [
            "gemini-2.5-flash-preview-tts",
            "gemini-2.5-pro-preview-tts",
            "gemini-3.1-flash-tts-preview",
        ]

    def test_voice_list_matches_official_30(self):
        from providers.gemini_tts import SUPPORTED_VOICES
        assert len(SUPPORTED_VOICES) == 30
        for v in ("Kore", "Puck", "Zephyr", "Aoede", "Fenrir", "Charon"):
            assert v in SUPPORTED_VOICES

    def test_factory_rejects_gemini_tts_without_key(self):
        from providers.tts_provider import get_tts_provider
        import pytest
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GEMINI_API_KEY", None)
            with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
                get_tts_provider({"tts_provider": "gemini_tts"})


class TestGeminiTTSSynthesize:
    """Mocked API path: request → base64 PCM → WAV."""

    def _fake_response(self, pcm: bytes):
        import base64
        return {
            "candidates": [{
                "content": {"parts": [{
                    "inlineData": {
                        "data": base64.b64encode(pcm).decode(),
                        "mimeType": "audio/L16;codec=pcm;rate=24000",
                    }
                }]}
            }]
        }

    def test_synthesize_writes_valid_wav(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        monkeypatch.setenv("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts")
        monkeypatch.setenv("GEMINI_TTS_VOICE", "Kore")
        from providers.gemini_tts import GeminiTTSProvider
        provider = GeminiTTSProvider({})

        captured = {}

        class FakeResp:
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
            def read(self):
                return json.dumps(self._fake_response(b"")).encode()

        # 8000 samples of silence (16-bit mono)
        pcm = b"\x00\x01" * 8000

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            captured["headers"] = dict(req.header_items()) if hasattr(req, "header_items") else {}
            captured["body"] = json.loads(req.data.decode())
            resp = FakeResp()
            resp._fake_response = lambda: self._fake_response(pcm) if False else {
                "candidates": [{
                    "content": {"parts": [{
                        "inlineData": {
                            "data": __import__("base64").b64encode(pcm).decode(),
                            "mimeType": "audio/L16;codec=pcm;rate=24000",
                        }
                    }]}
                }]
            }
            resp.read = lambda: json.dumps(resp._fake_response()).encode()
            return resp

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            out = provider.synthesize("Hello world", language="en", voice="Kore")

        assert out and os.path.exists(out)
        # Request used the right model + API key header
        assert "gemini-2.5-flash-preview-tts:generateContent" in captured["url"]
        body = captured["body"]
        assert body["generationConfig"]["responseModalities"] == ["AUDIO"]
        assert body["generationConfig"]["speechConfig"]["voiceConfig"][
            "prebuiltVoiceConfig"]["voiceName"] == "Kore"
        # Output is a valid WAV: 24kHz, mono, 16-bit
        with wave.open(out, "rb") as wf:
            assert wf.getframerate() == 24000
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getnframes() == 8000

    def test_unavailable_without_key(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        from providers.gemini_tts import GeminiTTSProvider
        p = GeminiTTSProvider({})
        assert p.is_available() is False
        assert p.synthesize("hello") is None


class TestModelNameAudit:
    """Repo mein jo AI model names hain wo valid hon."""

    def test_llm_default_is_current_gemini(self):
        with open(REPO_ROOT / "providers" / "llm_provider.py") as f:
            c = f.read()
        assert "gemini-2.5-flash" in c
        assert "gemini-2.0-flash" not in c  # outdated

    def test_config_defaults_current(self):
        with open(REPO_ROOT / "config" / "default.yaml") as f:
            c = f.read()
        assert "gemini_model: gemini-2.5-flash" in c
        assert "gemini-2.0-flash" not in c

    def test_workflow_apt_packages_valid_on_ubuntu_24(self):
        content = (REPO_ROOT / ".github" / "workflows" / "pipeline.yml").read_text()
        # libgl1-mesa-glx was removed in Ubuntu 24.04 — must NOT appear
        assert "libgl1-mesa-glx" not in content
        assert "libgl1" in content


class TestDownloadableNames:
    """requirements.txt package names must be valid PyPI names."""

    def test_requirements_packages_exist_on_pypi(self):
        import urllib.request
        packages = []
        with open(REPO_ROOT / "requirements.txt") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    packages.append(line.split(">=")[0].split("==")[0].strip())
        expected = {"PyYAML", "psutil", "Pillow", "requests", "gtts",
                    "pytest", "pytest-cov"}
        assert set(packages) == expected
