"""
Configuration loader — reads YAML configs and environment variables.

Merges default config with environment-specific overrides and validates
that all required secrets are present.
"""
import os
import yaml
from pathlib import Path
from typing import Any, Dict, Optional


class ConfigError(Exception):
    """Raised when configuration is missing or invalid."""


class ConfigLoader:
    """Load and merge configuration from YAML files and environment variables."""

    DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config" / "default.yaml"
    BLENDER_CONFIG_PATH = Path(__file__).parent.parent / "config" / "blender_settings.yaml"

    REQUIRED_SECRETS = [
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHANNEL_ID",
    ]

    OPTIONAL_SECRETS = [
        "OPENAI_API_KEY",
        "ELEVENLABS_API_KEY",
        "HF_TOKEN",
        "REPLICATE_API_TOKEN",
    ]

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = Path(config_path) if config_path else self.DEFAULT_CONFIG_PATH
        self._config: Dict[str, Any] = {}
        self.load()

    def load(self) -> Dict[str, Any]:
        """Load configuration from YAML and merge environment variables."""
        if not self.config_path.exists():
            raise ConfigError(f"Config file not found: {self.config_path}")

        with open(self.config_path, "r") as f:
            self._config = yaml.safe_load(f) or {}

        # Load Blender settings
        if self.BLENDER_CONFIG_PATH.exists():
            with open(self.BLENDER_CONFIG_PATH, "r") as f:
                blender_cfg = yaml.safe_load(f) or {}
            self._config.setdefault("blender", {}).update(blender_cfg)

        # Merge environment variables (highest priority)
        env_overrides = {
            "telegram_bot_token": os.environ.get("TELEGRAM_BOT_TOKEN"),
            "telegram_channel_id": os.environ.get("TELEGRAM_CHANNEL_ID"),
            "openai_api_key": os.environ.get("OPENAI_API_KEY"),
            "elevenlabs_api_key": os.environ.get("ELEVENLABS_API_KEY"),
            "hf_token": os.environ.get("HF_TOKEN"),
            "replicate_api_token": os.environ.get("REPLICATE_API_TOKEN"),
        }
        for key, value in env_overrides.items():
            if value is not None:
                self._config[key] = value

        return self._config

    def validate_secrets(self) -> bool:
        """Check that all required secrets are present."""
        missing = []
        for secret in self.REQUIRED_SECRETS:
            env_val = os.environ.get(secret)
            cfg_val = self._config.get(secret.lower())
            if not env_val and not cfg_val:
                missing.append(secret)
        if missing:
            raise ConfigError(f"Missing required secrets: {', '.join(missing)}")
        return True

    @property
    def config(self) -> Dict[str, Any]:
        return self._config

    def get(self, key: str, default: Any = None) -> Any:
        return self._config.get(key, default)

    def get_blender_setting(self, key: str, default: Any = None) -> Any:
        return self._config.get("blender", {}).get(key, default)

    def get_render_config(self) -> Dict[str, Any]:
        return self._config.get("render", {})

    def get_telegram_config(self) -> Dict[str, Any]:
        return {
            "bot_token": self._config.get("telegram_bot_token", ""),
            "channel_id": self._config.get("telegram_channel_id", ""),
        }
