"""Configuration management for quota-tracker."""

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from quota_tracker.core.constants import (
    DEFAULT_CONFIG_DIR,
    DEFAULT_DB_PATH,
    DEFAULT_WEB_HOST,
    DEFAULT_WEB_PORT,
)


class ProviderConfig(BaseModel):
    """Configuration for a specific AI provider."""

    enabled: bool = True
    home_path: Path
    active_probe_enabled: bool = True
    passive_sync_enabled: bool = True
    options: dict[str, Any] = Field(default_factory=dict)


class GlobalConfig(BaseModel):
    """Global daemon settings."""

    active_probe_interval_minutes: int = 60
    passive_sync_interval_minutes: int = 15
    web_host: str = DEFAULT_WEB_HOST
    web_port: int = DEFAULT_WEB_PORT
    database_path: Path = DEFAULT_DB_PATH
    log_level: str = "INFO"


class AppConfig(BaseModel):
    """Main application configuration."""

    global_settings: GlobalConfig = Field(default_factory=GlobalConfig)
    providers: dict[str, ProviderConfig] = Field(default_factory=dict)

    @classmethod
    def get_default_config(cls) -> "AppConfig":
        """Generate default configuration with standard provider paths."""
        home = Path.home()
        return cls(
            providers={
                "gemini": ProviderConfig(home_path=home / ".gemini"),
                "codex": ProviderConfig(home_path=home / ".codex"),
                "copilot": ProviderConfig(home_path=home / ".copilot"),
            }
        )

    def save(self, path: Path | None = None) -> None:
        """
        Save configuration to JSON file.

        Args:
            path: Optional path to save to.
                 Defaults to ~/.config/quota-tracker/config.json.
        """
        if path is None:
            path = DEFAULT_CONFIG_DIR / "config.json"

        path.parent.mkdir(parents=True, exist_ok=True)
        content = self.model_dump_json(indent=2)
        path.write_text(content, encoding="utf-8")

    @classmethod
    def load(cls, path: Path | None = None) -> "AppConfig":
        """
        Load configuration from JSON file.

        If the file does not exist or is invalid, returns default configuration.

        Args:
            path: Optional path to load from.
                 Defaults to ~/.config/quota-tracker/config.json.

        Returns:
            AppConfig instance.
        """
        if path is None:
            path = DEFAULT_CONFIG_DIR / "config.json"

        if not path.exists():
            return cls.get_default_config()

        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return cls.model_validate(data)
        except Exception:
            # Fallback to default if load fails
            return cls.get_default_config()
