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
