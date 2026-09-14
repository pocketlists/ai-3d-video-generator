"""Tests for configuration loading and validation."""
import os
import pytest
import yaml
from pathlib import Path

from controller.config_loader import ConfigLoader, ConfigError


def test_config_loader_initialization():
    """ConfigLoader can be instantiated."""
    config = ConfigLoader()
    assert config is not None
    assert isinstance(config.config, dict)


def test_config_has_pipeline_settings():
    """Config contains pipeline settings."""
    config = ConfigLoader()
    assert "pipeline" in config.config
    assert config.config["pipeline"]["fps"] == 24
    assert config.config["pipeline"]["total_frames"] == 1440


def test_config_has_render_settings():
    """Config contains render settings."""
    config = ConfigLoader()
    assert "render" in config.config
    assert config.config["render"]["engine"] == "BLENDER_EEVEE"


def test_config_has_blender_settings():
    """Config merges Blender settings."""
    config = ConfigLoader()
    blender = config.get_blender_setting("engine")
    assert blender == "BLENDER_EEVEE"


def test_config_get_with_default():
    """Config.get returns default for missing keys."""
    config = ConfigLoader()
    assert config.get("nonexistent_key", "default_val") == "default_val"


def test_config_get_render_config():
    """get_render_config returns render dict."""
    config = ConfigLoader()
    render = config.get_render_config()
    assert "engine" in render
    assert "samples" in render


def test_config_get_telegram_config():
    """get_telegram_config returns telegram dict."""
    config = ConfigLoader()
    tg = config.get_telegram_config()
    assert "bot_token" in tg
    assert "channel_id" in tg


def test_config_validate_secrets_missing():
    """validate_secrets raises when required secrets are missing."""
    config = ConfigLoader()
    # Clear any environment secrets for this test
    old_token = os.environ.pop("TELEGRAM_BOT_TOKEN", None)
    old_channel = os.environ.pop("TELEGRAM_CHANNEL_ID", None)
    try:
        with pytest.raises(ConfigError):
            config.validate_secrets()
    finally:
        if old_token:
            os.environ["TELEGRAM_BOT_TOKEN"] = old_token
        if old_channel:
            os.environ["TELEGRAM_CHANNEL_ID"] = old_channel


def test_config_validate_secrets_present():
    """validate_secrets passes when secrets are in env."""
    os.environ["TELEGRAM_BOT_TOKEN"] = "test_token"
    os.environ["TELEGRAM_CHANNEL_ID"] = "test_channel"
    config = ConfigLoader()
    assert config.validate_secrets() is True
    del os.environ["TELEGRAM_BOT_TOKEN"]
    del os.environ["TELEGRAM_CHANNEL_ID"]
