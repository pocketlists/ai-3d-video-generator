"""
LLM Provider — abstraction for AI planning via Gemini, OpenAI, or template fallback.

Supports:
- GeminiProvider: Google Gemini API
- OpenAIProvider: OpenAI GPT API
- TemplateProvider: Local template-based planning (no API needed)

The provider is selected via configuration: LLM_PROVIDER=gemini|openai|template
"""
import json
import os
import urllib.request
import urllib.error
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from utils.retry import retry
from utils.logger import PipelineLogger


class LLMError(Exception):
    """Raised when an LLM API call fails."""
    pass


class LLMProvider(ABC):
    """Abstract base for LLM providers."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = PipelineLogger("llm_provider")

    @abstractmethod
    def generate_plan(self, prompt: str) -> Dict[str, Any]:
        """Generate a video production plan from a prompt."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this provider is configured and available."""
        ...


class GeminiProvider(LLMProvider):
    """Google Gemini API provider."""

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = config.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY", "")
        self.model = config.get("gemini_model", "gemini-1.5-flash")

    def is_available(self) -> bool:
        return bool(self.api_key)

    @retry(max_attempts=3, initial_delay=2.0, backoff_factor=2.0,
           retryable_messages=["timeout", "429", "503", "rate_limit", "temporarily"])
    def generate_plan(self, prompt: str) -> Dict[str, Any]:
        if not self.api_key:
            raise LLMError("GEMINI_API_KEY not configured")

        system_prompt = (
            "You are a 3D video director. Create a JSON plan for a 1-minute "
            "low-poly 3D video. Include scenes, characters, environments, props, "
            "camera movements, and narration. Keep it suitable for CPU rendering. "
            "Respond with valid JSON only."
        )

        payload = json.dumps({
            "contents": [{"parts": [{"text": system_prompt + "\n\n" + prompt}]}],
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 2000},
        }).encode()

        url = f"{self.BASE_URL}/{self.model}:generateContent?key={self.api_key}"
        req = urllib.request.Request(url, data=payload)
        req.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode())
            text = result["candidates"][0]["content"]["parts"][0]["text"]
            if "{" in text:
                start = text.index("{")
                end = text.rindex("}") + 1
                plan = json.loads(text[start:end])
            else:
                plan = TemplateProvider(self.config).generate_plan(prompt)
            plan["ai_generated"] = True
            plan["provider"] = "gemini"
            return plan
        except urllib.error.HTTPError as e:
            error_body = e.read().decode() if e.fp else str(e)
            raise LLMError(f"Gemini HTTP {e.code}: {error_body}")
        except urllib.error.URLError as e:
            raise LLMError(f"Gemini URL error: {e}")
        except (KeyError, json.JSONDecodeError) as e:
            raise LLMError(f"Gemini response parse error: {e}")


class OpenAIProvider(LLMProvider):
    """OpenAI GPT API provider."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = config.get("openai_api_key") or os.environ.get("OPENAI_API_KEY", "")
        self.model = config.get("openai_model", "gpt-4o-mini")

    def is_available(self) -> bool:
        return bool(self.api_key)

    @retry(max_attempts=3, initial_delay=2.0, backoff_factor=2.0,
           retryable_messages=["timeout", "429", "503", "rate_limit"])
    def generate_plan(self, prompt: str) -> Dict[str, Any]:
        if not self.api_key:
            raise LLMError("OPENAI_API_KEY not configured")

        system_msg = (
            "You are a 3D video director. Create a JSON plan for a 1-minute "
            "low-poly 3D video. Include scenes, characters, environments, props, "
            "camera movements, and narration. Respond with valid JSON only."
        )
        payload = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.7,
            "max_tokens": 2000,
        }).encode()

        req = urllib.request.Request("https://api.openai.com/v1/chat/completions", data=payload)
        req.add_header("Authorization", f"Bearer {self.api_key}")
        req.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode())
            content = result["choices"][0]["message"]["content"]
            if "{" in content:
                start = content.index("{")
                end = content.rindex("}") + 1
                plan = json.loads(content[start:end])
            else:
                plan = TemplateProvider(self.config).generate_plan(prompt)
            plan["ai_generated"] = True
            plan["provider"] = "openai"
            return plan
        except urllib.error.HTTPError as e:
            error_body = e.read().decode() if e.fp else str(e)
            raise LLMError(f"OpenAI HTTP {e.code}: {error_body}")
        except urllib.error.URLError as e:
            raise LLMError(f"OpenAI URL error: {e}")
        except (KeyError, json.JSONDecodeError) as e:
            raise LLMError(f"OpenAI response parse error: {e}")


class TemplateProvider(LLMProvider):
    """Local template-based planning — no API needed, always available."""

    def is_available(self) -> bool:
        return True

    def generate_plan(self, prompt: str) -> Dict[str, Any]:
        return {
            "title": f"Low-poly video: {prompt[:50]}",
            "prompt": prompt,
            "ai_generated": False,
            "provider": "template",
            "estimated_duration": 60,
            "fps": 24,
            "total_frames": 1440,
            "scenes": [
                {
                    "id": 1, "name": "opening_shot", "duration_sec": 15,
                    "description": f"Wide establishing shot of {prompt}",
                    "camera": {"type": "static", "location": [8, -8, 4], "target": [0, 0, 1]},
                    "characters": [],
                    "environment": {"type": "outdoor", "prompt": prompt},
                    "props": [],
                    "narration": "A beautiful scene unfolds.",
                },
                {
                    "id": 2, "name": "main_action", "duration_sec": 30,
                    "description": "Main action with characters",
                    "camera": {"type": "orbit", "location": [5, -5, 3], "target": [0, 0, 1]},
                    "characters": [{"name": "hero", "prompt": "boy in black hoodie", "position": [0, 0, 0]}],
                    "environment": {"type": "outdoor", "prompt": prompt},
                    "props": [{"name": "crate", "type": "box", "prompt": "wooden crate", "position": [1, 1, 0]}],
                    "narration": "The hero explores the landscape.",
                },
                {
                    "id": 3, "name": "closing_shot", "duration_sec": 15,
                    "description": "Closing wide shot",
                    "camera": {"type": "static", "location": [10, -10, 5], "target": [0, 0, 1]},
                    "characters": [],
                    "environment": {"type": "outdoor", "prompt": prompt},
                    "props": [],
                    "narration": "The scene fades to a close.",
                },
            ],
        }


def get_llm_provider(config: Dict[str, Any]) -> LLMProvider:
    """Factory: select LLM provider based on configuration."""
    provider_name = config.get("llm_provider", "template")
    if provider_name == "gemini":
        provider = GeminiProvider(config)
        if provider.is_available():
            return provider
    elif provider_name == "openai":
        provider = OpenAIProvider(config)
        if provider.is_available():
            return provider
    return TemplateProvider(config)
