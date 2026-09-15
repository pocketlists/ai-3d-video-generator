"""
LLM Provider — no silent fallback, robust JSON, style-aware prompts.

If LLM_PROVIDER=gemini and Gemini fails:
1. Retry with exponential backoff
2. If still failing: escalate to Telegram (WAITING_FOR_EXTERNAL_RESPONSE)
3. DO NOT silently switch to TemplateProvider

TemplateProvider is ONLY used when LLM_PROVIDER=template
or ALLOW_TEMPLATE_FALLBACK=true is explicitly configured.
"""
import json
import os
import re
import urllib.request
import urllib.error
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Tuple

from utils.retry import retry
from utils.logger import PipelineLogger
from utils.error_classifier import classify_error, should_retry, should_escalate


class LLMError(Exception):
    pass


class LLMProvider(ABC):
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = PipelineLogger("llm_provider")

    @abstractmethod
    def generate_plan(self, prompt: str, style: str = "low-poly") -> Dict[str, Any]:
        ...

    @abstractmethod
    def is_available(self) -> bool:
        ...

    @abstractmethod
    def capabilities(self) -> Dict[str, bool]:
        ...

    def health_check(self) -> bool:
        return self.is_available()


class GeminiProvider(LLMProvider):
    """Google Gemini API — no silent fallback."""

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = config.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY", "")
        self.model = config.get("gemini_model") or os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def capabilities(self) -> Dict[str, bool]:
        return {"text_generation": True, "json_output": True, "streaming": False}

    def generate_plan(self, prompt: str, style: str = "low-poly") -> Dict[str, Any]:
        if not self.api_key:
            raise LLMError("GEMINI_API_KEY not configured")

        system_prompt = self._build_system_prompt(style)
        payload = json.dumps({
            "contents": [{"parts": [{"text": system_prompt + "\n\n" + prompt}]}],
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 2000,
                                  "responseMimeType": "application/json"},
        }).encode()

        url = f"{self.BASE_URL}/{self.model}:generateContent?key={self.api_key}"
        req = urllib.request.Request(url, data=payload)
        req.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode())
            text = result["candidates"][0]["content"]["parts"][0]["text"]
            plan = self._parse_json_response(text)
            plan["provider"] = "gemini"
            plan["ai_generated"] = True
            self._validate_plan(plan)
            return plan
        except urllib.error.HTTPError as e:
            error_body = e.read().decode() if e.fp else str(e)
            raise LLMError(f"Gemini HTTP {e.code}: {error_body}")
        except urllib.error.URLError as e:
            raise LLMError(f"Gemini network error: {e}")
        except (KeyError, IndexError) as e:
            raise LLMError(f"Gemini response parse error: {e}")

    def _build_system_prompt(self, style: str) -> str:
        return (
            f"You are a 3D video director creating a plan for a 1-minute {style} 3D video.\n"
            "Respond with valid JSON containing:\n"
            "- title: string\n"
            "- estimated_duration: number (seconds, ~60)\n"
            "- fps: number (24)\n"
            "- total_frames: number (1440)\n"
            "- scenes: array of objects with id, name, duration_sec, description, "
            "camera (type, location, target), characters (name, prompt, position), "
            "environment (type, prompt), props (name, type, prompt, position), narration\n\n"
            f"Visual style: {style}\n"
            "Keep suitable for CPU rendering."
        )

    def _parse_json_response(self, text: str) -> Dict:
        """Robust JSON extraction — tries multiple strategies."""
        # Strategy 1: Direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Strategy 2: Find outermost braces (first { to last })
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end+1])
            except json.JSONDecodeError:
                pass

        # Strategy 3: Extract innermost JSON blocks with regex
        matches = re.findall(r'\{[^{}]*\}', text, re.DOTALL)
        if not matches:
            # Try finding outermost braces
            start = text.find('{')
            end = text.rfind('}')
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end+1])
                except json.JSONDecodeError:
                    pass
            raise LLMError(f"Could not extract JSON from response: {text[:200]}")

        # Try each match, prefer the longest
        for match in sorted(matches, key=len, reverse=True):
            try:
                return json.loads(match)
            except json.JSONDecodeError:
                continue

        raise LLMError(f"JSON parse failed for all extraction strategies")

    def _validate_plan(self, plan: Dict) -> None:
        """Validate plan structure. Raises LLMError if invalid."""
        if "scenes" not in plan or not isinstance(plan["scenes"], list):
            raise LLMError("Plan missing 'scenes' array")
        if not plan["scenes"]:
            raise LLMError("Plan has empty scenes")
        for i, scene in enumerate(plan["scenes"]):
            if "duration_sec" not in scene or scene["duration_sec"] <= 0:
                raise LLMError(f"Scene {i} has invalid duration")
            if "id" not in scene:
                raise LLMError(f"Scene {i} missing id")


class OpenAIProvider(LLMProvider):
    """OpenAI GPT API."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = config.get("openai_api_key") or os.environ.get("OPENAI_API_KEY", "")
        self.model = config.get("openai_model", "gpt-4o-mini")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def capabilities(self) -> Dict[str, bool]:
        return {"text_generation": True, "json_output": True, "streaming": False}

    def generate_plan(self, prompt: str, style: str = "low-poly") -> Dict[str, Any]:
        if not self.api_key:
            raise LLMError("OPENAI_API_KEY not configured")

        system_msg = (
            f"You are a 3D video director. Create a JSON plan for a 1-minute {style} 3D video. "
            "Include title, scenes (with id, name, duration_sec, camera, characters, environment, props, narration), "
            "fps (24), total_frames (1440). Respond with valid JSON only."
        )
        payload = json.dumps({
            "model": self.model,
            "messages": [{"role": "system", "content": system_msg},
                         {"role": "user", "content": prompt}],
            "temperature": 0.7, "max_tokens": 2000,
        }).encode()

        req = urllib.request.Request("https://api.openai.com/v1/chat/completions", data=payload)
        req.add_header("Authorization", f"Bearer {self.api_key}")
        req.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode())
            content = result["choices"][0]["message"]["content"]
            plan = GeminiProvider(self.config)._parse_json_response(content)
            plan["provider"] = "openai"
            plan["ai_generated"] = True
            return plan
        except urllib.error.HTTPError as e:
            raise LLMError(f"OpenAI HTTP {e.code}: {e.read().decode()[:200]}")
        except urllib.error.URLError as e:
            raise LLMError(f"OpenAI network error: {e}")


class TemplateProvider(LLMProvider):
    """Template-based planning — only used when explicitly configured."""

    def is_available(self) -> bool:
        return True

    def capabilities(self) -> Dict[str, bool]:
        return {"text_generation": True, "json_output": True, "streaming": False}

    def generate_plan(self, prompt: str, style: str = "low-poly") -> Dict[str, Any]:
        return {
            "title": f"{style} video: {prompt[:50]}",
            "prompt": prompt, "style": style,
            "ai_generated": False, "provider": "template",
            "estimated_duration": 60, "fps": 24, "total_frames": 1440,
            "scenes": [
                {"id": 1, "name": "opening", "duration_sec": 15,
                 "description": f"Wide shot of {prompt}", "style": style,
                 "camera": {"type": "static", "location": [8, -8, 4], "target": [0, 0, 1]},
                 "characters": [], "environment": {"type": "outdoor", "prompt": prompt},
                 "props": [], "narration": "A beautiful scene unfolds."},
                {"id": 2, "name": "main_action", "duration_sec": 30,
                 "description": "Main action", "style": style,
                 "camera": {"type": "orbit", "location": [5, -5, 3], "target": [0, 0, 1]},
                 "characters": [{"name": "hero", "prompt": f"{style} character", "position": [0, 0, 0]}],
                 "environment": {"type": "outdoor", "prompt": prompt},
                 "props": [{"name": "prop1", "type": "box", "prompt": "crate", "position": [1, 1, 0]}],
                 "narration": "The hero explores."},
                {"id": 3, "name": "closing", "duration_sec": 15,
                 "description": "Closing shot", "style": style,
                 "camera": {"type": "static", "location": [10, -10, 5], "target": [0, 0, 1]},
                 "characters": [], "environment": {"type": "outdoor", "prompt": prompt},
                 "props": [], "narration": "The scene fades."},
            ],
        }


def get_llm_provider(config: Dict[str, Any]) -> LLMProvider:
    """
    Factory: select LLM provider.
    NO silent fallback to template — if gemini is requested, escalate on failure.
    """
    provider_name = config.get("llm_provider") or os.environ.get("LLM_PROVIDER", "template")
    allow_fallback = config.get("allow_template_fallback", False) or os.environ.get("ALLOW_TEMPLATE_FALLBACK", "false").lower() == "true"

    if provider_name == "gemini":
        provider = GeminiProvider(config)
        if provider.is_available():
            return provider
        if allow_fallback:
            return TemplateProvider(config)
        raise LLMError("LLM_PROVIDER=gemini but GEMINI_API_KEY not set. Set ALLOW_TEMPLATE_FALLBACK=true to use template fallback.")

    if provider_name == "openai":
        provider = OpenAIProvider(config)
        if provider.is_available():
            return provider
        if allow_fallback:
            return TemplateProvider(config)
        raise LLMError("LLM_PROVIDER=openai but OPENAI_API_KEY not set. Set ALLOW_TEMPLATE_FALLBACK=true to use template fallback.")

    return TemplateProvider(config)
