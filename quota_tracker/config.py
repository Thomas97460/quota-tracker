"""Configuration schema, persistence, and sanitization helpers."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from quota_tracker.paths import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_DB_PATH,
    DEFAULT_WEB_HOST,
    DEFAULT_WEB_PORT,
)


class ProviderConfig(BaseModel):
    """Provider-specific safe configuration."""

    enabled: bool = True
    home_path: str
    active_probe_enabled: bool = False
    passive_sync_enabled: bool = True
    safe_options: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class DaemonConfig(BaseModel):
    """Global daemon settings."""

    sync_interval_minutes: int = 5
    active_probe_interval_minutes: int = 5
    passive_sync_interval_minutes: int = 15
    web_host: str = DEFAULT_WEB_HOST
    web_port: int = DEFAULT_WEB_PORT
    database_path: str = str(DEFAULT_DB_PATH)
    log_level: str = "INFO"


class AppConfig(BaseModel):
    """Root application configuration."""

    daemon: DaemonConfig = Field(default_factory=DaemonConfig)
    gemini: ProviderConfig = Field(default_factory=lambda: ProviderConfig(home_path="~/.gemini"))
    codex: ProviderConfig = Field(default_factory=lambda: ProviderConfig(home_path="~/.codex"))
    copilot: ProviderConfig = Field(default_factory=lambda: ProviderConfig(home_path="~/.copilot"))


def default_config_json() -> str:
    """Return the default JSON config content."""

    return AppConfig().model_dump_json(indent=2)


def config_file_path() -> str:
    """Return the default config file path."""

    return str(DEFAULT_CONFIG_PATH)


def load_config(path: str | None = None) -> AppConfig:
    """Load config from disk or return defaults when absent."""

    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    if not config_path.exists():
        return AppConfig()
    data = json.loads(config_path.read_text())
    return AppConfig.model_validate(data)


def save_config(config: AppConfig, path: str | None = None) -> None:
    """Persist config to disk."""

    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(config.model_dump_json(indent=2) + "\n")


def sanitized_config_json(config: AppConfig) -> str:
    """Return sanitized config JSON for CLI/API display."""

    return config.model_dump_json(indent=2)
