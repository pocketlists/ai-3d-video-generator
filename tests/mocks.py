"""
Mock providers for testing — NEVER used in production code.

Tests must NOT require paid APIs. These mocks simulate provider behavior.
"""
from typing import Any, Dict, Optional
from providers.llm_provider import LLMProvider, TemplateProvider
from providers.asset_provider import ThreeDAssetProvider, CachedAsset


class MockGeminiProvider(LLMProvider):
    """Mock Gemini — returns valid plans without API calls."""

    def is_available(self) -> bool:
        return True

    def capabilities(self) -> Dict[str, bool]:
        return {"text_generation": True, "json_output": True}

    def generate_plan(self, prompt: str, style: str = "low-poly") -> Dict[str, Any]:
        return {
            "title": f"Mock {style} plan",
            "provider": "gemini", "ai_generated": True,
            "estimated_duration": 60, "fps": 24, "total_frames": 1440,
            "scenes": [
                {"id": 1, "name": "test", "duration_sec": 20,
                 "description": prompt, "camera": {"type": "static"},
                 "characters": [], "environment": {"type": "outdoor"},
                 "props": [], "narration": "mock narration"},
            ],
        }


class MockFailingGeminiProvider(LLMProvider):
    """Mock Gemini that always fails — for testing escalation."""

    def is_available(self) -> bool:
        return True

    def capabilities(self) -> Dict[str, bool]:
        return {"text_generation": True, "json_output": True}

    def generate_plan(self, prompt: str, style: str = "low-poly") -> Dict[str, Any]:
        from providers.llm_provider import LLMError
        raise LLMError("429 RESOURCE_EXHAUSTED — mock rate limit")


class MockObjaverseProvider(ThreeDAssetProvider):
    """Mock Objaverse — returns fake GLB data without network."""

    def is_available(self) -> bool:
        return True

    def capabilities(self) -> Dict[str, bool]:
        return {"search": True, "text_to_3d": False, "supports_glb": True}

    def generate_asset(self, prompt: str, asset_type: str, name: str) -> Optional[CachedAsset]:
        import os, time
        fake_glb = b"glTF" + b"\x02\x00\x00\x00" + b"\x64\x00\x00\x00" + \
                   b"\x20\x00\x00\x00JSON" + \
                   b'{"meshes":[],"materials":[]}'
        path = self.cache_dir / asset_type / f"{name}.glb"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            f.write(fake_glb)
        return CachedAsset(
            asset_id=f"mock_{name}", name=name, prompt=prompt,
            provider="objaverse", file_path=str(path), format="glb",
            file_size=len(fake_glb), created_at=time.time(),
            validation_status="valid",
            metadata={"source": "mock", "license": "CC-BY-4.0 (mock)"},
        )


class MockTTSProvider:
    """Mock TTS — writes fake audio files."""

    def is_available(self) -> bool:
        return True

    def synthesize(self, text: str, language: str = "en") -> str:
        import os, tempfile
        path = os.path.join(tempfile.mkdtemp(), f"mock_tts_{hash(text) % 10000}.mp3")
        with open(path, "wb") as f:
            f.write(b"ID3mockaudio")  # fake mp3 header
        return path


class MockTelegramProvider:
    """Mock Telegram — records sent messages without network."""

    def __init__(self):
        self.sent_messages = []

    def is_available(self) -> bool:
        return True

    def send_message(self, text: str) -> bool:
        self.sent_messages.append(text)
        return True
