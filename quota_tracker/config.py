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


class ModelPricing(BaseModel):
    """Token pricing per 1M tokens in USD."""

    input_1m: float = 0.0
    output_1m: float = 0.0
    cached_1m: float = 0.0


def get_default_pricing() -> dict[str, ModelPricing]:
    """Return default pricing for known models as of 2026-05-09."""

    # Key format: "provider_id:model_name"
    # Prices are per 1M tokens in USD
    defaults = {
        # OpenAI (via Codex or future direct provider)
        "codex:gpt-5.5": ModelPricing(input_1m=5.00, cached_1m=0.50, output_1m=30.00),
        "codex:gpt-5.5-pro": ModelPricing(input_1m=30.00, output_1m=180.00),
        "codex:gpt-5.4": ModelPricing(input_1m=2.50, cached_1m=0.25, output_1m=15.00),
        "codex:gpt-5.4-mini": ModelPricing(input_1m=0.75, cached_1m=0.075, output_1m=4.50),
        "codex:gpt-5.4-nano": ModelPricing(input_1m=0.20, cached_1m=0.02, output_1m=1.25),
        "codex:gpt-5.4-pro": ModelPricing(input_1m=30.00, output_1m=180.00),
        "codex:gpt-5.3-codex": ModelPricing(input_1m=1.75, cached_1m=0.175, output_1m=14.00),
        "codex:gpt-5.2-codex": ModelPricing(input_1m=1.75, cached_1m=0.175, output_1m=14.00),
        "codex:gpt-5.2": ModelPricing(input_1m=2.50, cached_1m=0.25, output_1m=15.00),
        "codex:gpt-5.1-codex": ModelPricing(input_1m=1.75, cached_1m=0.175, output_1m=14.00),
        "codex:gpt-5.1-codex-max": ModelPricing(input_1m=3.50, cached_1m=0.35, output_1m=28.00),
        "codex:gpt-5.1-codex-mini": ModelPricing(input_1m=0.75, cached_1m=0.075, output_1m=4.50),
        "codex:gpt-5-codex": ModelPricing(input_1m=1.75, cached_1m=0.175, output_1m=14.00),
        # Anthropic (Claude)
        "claude:claude-opus-4-7": ModelPricing(input_1m=5.00, cached_1m=0.50, output_1m=25.00),
        "claude:claude-opus-4-6": ModelPricing(input_1m=5.00, cached_1m=0.50, output_1m=25.00),
        "claude:claude-opus-4-5": ModelPricing(input_1m=5.00, cached_1m=0.50, output_1m=25.00),
        "claude:claude-opus-4-1": ModelPricing(input_1m=15.00, cached_1m=1.50, output_1m=75.00),
        "claude:claude-sonnet-4-6": ModelPricing(input_1m=3.00, cached_1m=0.30, output_1m=15.00),
        "claude:claude-sonnet-4-5": ModelPricing(input_1m=3.00, cached_1m=0.30, output_1m=15.00),
        "claude:claude-sonnet-4": ModelPricing(input_1m=3.00, cached_1m=0.30, output_1m=15.00),
        "claude:claude-haiku-4.5": ModelPricing(input_1m=1.00, cached_1m=0.10, output_1m=5.00),
        "claude:claude-haiku-3.5": ModelPricing(input_1m=0.80, cached_1m=0.08, output_1m=4.00),
        "claude:claude-haiku-3": ModelPricing(input_1m=0.25, cached_1m=0.03, output_1m=1.25),
        # Google Gemini
        "gemini:gemini-3.1-pro-preview": ModelPricing(
            input_1m=3.60, cached_1m=0.36, output_1m=21.60
        ),
        "gemini:gemini-3-pro-preview": ModelPricing(input_1m=3.60, cached_1m=0.36, output_1m=21.60),
        "gemini:gemini-3-flash-preview": ModelPricing(
            input_1m=0.90, cached_1m=0.09, output_1m=5.40
        ),
        "gemini:gemini-3.1-flash-lite-preview": ModelPricing(
            input_1m=0.45, cached_1m=0.045, output_1m=2.70
        ),
        "gemini:gemini-2.5-pro": ModelPricing(input_1m=2.25, cached_1m=0.23, output_1m=18.00),
        "gemini:gemini-2.5-flash": ModelPricing(input_1m=0.54, cached_1m=0.05, output_1m=4.50),
        "gemini:gemini-2.5-flash-lite": ModelPricing(input_1m=0.18, cached_1m=0.02, output_1m=0.72),
        # GitHub Copilot
        "copilot:gpt-4.1": ModelPricing(input_1m=2.00, cached_1m=0.50, output_1m=8.00),
        "copilot:gpt-5-mini": ModelPricing(input_1m=0.25, cached_1m=0.025, output_1m=2.00),
        "copilot:gpt-5.2": ModelPricing(input_1m=1.75, cached_1m=0.175, output_1m=14.00),
        "copilot:gpt-5.2-codex": ModelPricing(input_1m=1.75, cached_1m=0.175, output_1m=14.00),
        "copilot:gpt-5.3-codex": ModelPricing(input_1m=1.75, cached_1m=0.175, output_1m=14.00),
        "copilot:gpt-5.4": ModelPricing(input_1m=2.50, cached_1m=0.25, output_1m=15.00),
        "copilot:gpt-5.4-mini": ModelPricing(input_1m=0.75, cached_1m=0.075, output_1m=4.50),
        "copilot:gpt-5.4-nano": ModelPricing(input_1m=0.20, cached_1m=0.02, output_1m=1.25),
        "copilot:gpt-5.5": ModelPricing(input_1m=5.00, cached_1m=0.50, output_1m=30.00),
        "copilot:claude-haiku-4.5": ModelPricing(input_1m=1.00, cached_1m=0.10, output_1m=5.00),
        "copilot:claude-sonnet-4": ModelPricing(input_1m=3.00, cached_1m=0.30, output_1m=15.00),
        "copilot:claude-sonnet-4-5": ModelPricing(input_1m=3.00, cached_1m=0.30, output_1m=15.00),
        "copilot:claude-sonnet-4-6": ModelPricing(input_1m=3.00, cached_1m=0.30, output_1m=15.00),
        "copilot:claude-opus-4-5": ModelPricing(input_1m=5.00, cached_1m=0.50, output_1m=25.00),
        "copilot:claude-opus-4-6": ModelPricing(input_1m=5.00, cached_1m=0.50, output_1m=25.00),
        "copilot:claude-opus-4-7": ModelPricing(input_1m=5.00, cached_1m=0.50, output_1m=25.00),
        "copilot:gemini-2.5-pro": ModelPricing(input_1m=1.25, cached_1m=0.125, output_1m=10.00),
        "copilot:gemini-3-flash": ModelPricing(input_1m=0.50, cached_1m=0.05, output_1m=3.00),
        "copilot:gemini-3.1-pro": ModelPricing(input_1m=2.00, cached_1m=0.20, output_1m=12.00),
    }

    return defaults


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
    claude: ProviderConfig = Field(default_factory=lambda: ProviderConfig(home_path="~/.claude"))
    pricing: dict[str, ModelPricing] = Field(default_factory=get_default_pricing)


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
