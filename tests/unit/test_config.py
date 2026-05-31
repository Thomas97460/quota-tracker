"""Tests for configuration defaults."""

from __future__ import annotations

from quota_tracker.config import AppConfig, get_default_pricing


def test_default_pricing_includes_claude_opus_4_8() -> None:
    pricing = get_default_pricing()

    for provider_id in ("claude", "copilot"):
        model_pricing = pricing[f"{provider_id}:claude-opus-4-8"]

        assert model_pricing.input_1m == 5.00
        assert model_pricing.cached_1m == 0.50
        assert model_pricing.output_1m == 25.00


def test_default_config_includes_antigravity() -> None:
    config = AppConfig()

    assert config.antigravity.home_path == "~/.gemini/antigravity-cli"


def test_default_pricing_includes_antigravity_gemini_models() -> None:
    pricing = get_default_pricing()

    assert pricing["antigravity:gemini-3-pro-preview"].input_1m == 3.60
    assert pricing["antigravity:gemini-2.5-flash"].output_1m == 4.50
