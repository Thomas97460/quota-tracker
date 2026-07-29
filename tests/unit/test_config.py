"""Tests for configuration defaults."""

from __future__ import annotations

from quota_tracker.config import (
    AppConfig,
    ModelPricing,
    get_default_pricing,
    load_config,
    save_config,
)


def test_default_pricing_includes_claude_opus_4_8() -> None:
    pricing = get_default_pricing()

    for provider_id in ("claude", "copilot"):
        model_pricing = pricing[f"{provider_id}:claude-opus-4-8"]

        assert model_pricing.input_1m == 5.00
        assert model_pricing.cached_1m == 0.50
        assert model_pricing.output_1m == 25.00


def test_default_pricing_includes_latest_codex_models() -> None:
    pricing = get_default_pricing()

    assert pricing["codex:gpt-5.6"] == ModelPricing(input_1m=5.00, cached_1m=0.50, output_1m=30.00)
    assert pricing["codex:gpt-5.6-sol"] == pricing["codex:gpt-5.6"]
    assert pricing["codex:gpt-5.6-terra"] == ModelPricing(
        input_1m=2.50, cached_1m=0.25, output_1m=15.00
    )
    assert pricing["codex:gpt-5.6-luna"] == ModelPricing(
        input_1m=1.00, cached_1m=0.10, output_1m=6.00
    )


def test_default_pricing_includes_claude_opus_5() -> None:
    pricing = get_default_pricing()

    for provider_id in ("claude", "antigravity"):
        assert pricing[f"{provider_id}:claude-opus-5"] == ModelPricing(
            input_1m=5.00, cached_1m=0.50, output_1m=25.00
        )


def test_default_pricing_includes_latest_gemini_models() -> None:
    pricing = get_default_pricing()

    expected = {
        "gemini-3.6-flash": ModelPricing(input_1m=1.50, cached_1m=0.15, output_1m=7.50),
        "gemini-3.5-flash": ModelPricing(input_1m=1.50, cached_1m=0.15, output_1m=9.00),
        "gemini-3.5-flash-lite": ModelPricing(input_1m=0.30, cached_1m=0.03, output_1m=2.50),
        "gemini-3.1-flash-lite": ModelPricing(input_1m=0.25, cached_1m=0.025, output_1m=1.50),
    }

    for provider_id in ("gemini", "antigravity"):
        for model_id, model_pricing in expected.items():
            assert pricing[f"{provider_id}:{model_id}"] == model_pricing


def test_default_config_includes_antigravity() -> None:
    config = AppConfig()

    assert config.antigravity.home_path == "~/.gemini/antigravity-cli"


def test_default_pricing_includes_antigravity_gemini_models() -> None:
    pricing = get_default_pricing()

    assert pricing["antigravity:gemini-3-pro-preview"].input_1m == 3.60
    assert pricing["antigravity:gemini-2.5-flash"].output_1m == 4.50
    assert pricing["antigravity:gemini-3.5-flash"].input_1m == 1.50
    assert pricing["antigravity:claude-opus-4.6"].input_1m == 5.00
    assert pricing["antigravity:gpt-oss"].input_1m == 2.00


def test_load_config_backfills_pricing_for_new_models(tmp_path) -> None:
    config_path = tmp_path / "config.json"
    # Simulate a config saved by an older release: explicit pricing, a custom
    # value, and missing the newer opus-4-8 model.
    saved = AppConfig()
    saved.pricing = {
        "claude:claude-opus-4-7": ModelPricing(input_1m=99.0, cached_1m=9.0, output_1m=99.0),
    }
    save_config(saved, str(config_path))

    loaded = load_config(str(config_path))

    # Saved price wins over the default for a model present in the file.
    assert loaded.pricing["claude:claude-opus-4-7"].input_1m == 99.0
    # A model absent from the saved file is backfilled from the defaults.
    assert loaded.pricing["claude:claude-opus-4-8"].output_1m == 25.00
