"""Unit tests for configuration management."""

from pathlib import Path

from quota_tracker.core.config import AppConfig
from quota_tracker.core.constants import DEFAULT_WEB_HOST, DEFAULT_WEB_PORT


def test_default_config() -> None:
    """Verify default configuration values."""
    config = AppConfig.get_default_config()
    assert config.global_settings.web_host == DEFAULT_WEB_HOST
    assert config.global_settings.web_port == DEFAULT_WEB_PORT
    assert "gemini" in config.providers
    assert "codex" in config.providers
    assert "copilot" in config.providers
    assert config.providers["gemini"].home_path == Path.home() / ".gemini"


def test_save_load_config(tmp_path: Path) -> None:
    """Verify saving and loading configuration."""
    config_path = tmp_path / "config.json"
    config = AppConfig.get_default_config()
    config.global_settings.web_port = 9999
    config.providers["gemini"].enabled = False

    config.save(config_path)
    assert config_path.exists()

    loaded_config = AppConfig.load(config_path)
    assert loaded_config.global_settings.web_port == 9999
    assert loaded_config.providers["gemini"].enabled is False
    assert loaded_config.providers["codex"].enabled is True


def test_load_nonexistent_returns_default(tmp_path: Path) -> None:
    """Verify loading non-existent config returns defaults."""
    config_path = tmp_path / "nonexistent.json"
    config = AppConfig.load(config_path)
    assert config.global_settings.web_port == DEFAULT_WEB_PORT


def test_load_invalid_returns_default(tmp_path: Path) -> None:
    """Verify loading invalid config returns defaults."""
    config_path = tmp_path / "invalid.json"
    config_path.write_text("invalid json", encoding="utf-8")
    config = AppConfig.load(config_path)
    assert config.global_settings.web_port == DEFAULT_WEB_PORT
