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

    assert pricing["codex:gpt-6-astra"] == ModelPricing(
        input_1m=10.00, cached_1m=1.00, output_1m=50.00
    )
    assert pricing["codex:gpt-5.6"] == ModelPricing(input_1m=4.00, cached_1m=0.40, output_1m=20.00)
    assert pricing["codex:gpt-5.6-sol"] == pricing["codex:gpt-5.6"]
    assert pricing["codex:gpt-5.6-terra"] == ModelPricing(
        input_1m=2.00, cached_1m=0.20, output_1m=12.00
    )
    assert pricing["codex:gpt-5.6-luna"] == ModelPricing(
        input_1m=0.20, cached_1m=0.02, output_1m=1.20
    )
    assert pricing["codex:gpt-5.2"] == ModelPricing(input_1m=1.75, cached_1m=0.175, output_1m=14.00)


def test_default_pricing_includes_claude_opus_5() -> None:
    pricing = get_default_pricing()

    for provider_id in ("claude", "antigravity"):
        assert pricing[f"{provider_id}:claude-opus-5"] == ModelPricing(
            input_1m=5.00, cached_1m=0.50, output_1m=25.00
        )


def test_default_pricing_uses_current_claude_sonnet_5_rate() -> None:
    pricing = get_default_pricing()

    for provider_id in ("claude", "antigravity", "copilot"):
        assert pricing[f"{provider_id}:claude-sonnet-5"] == ModelPricing(
            input_1m=2.00, cached_1m=0.20, output_1m=10.00
        )


def test_default_pricing_includes_latest_gemini_models() -> None:
    pricing = get_default_pricing()

    expected = {
        "gemini-3.7-flash": ModelPricing(input_1m=0.75, cached_1m=0.075, output_1m=3.75),
        "gemini-3.6-flash": ModelPricing(input_1m=0.75, cached_1m=0.075, output_1m=3.75),
        "gemini-3.5-flash": ModelPricing(input_1m=1.50, cached_1m=0.15, output_1m=9.00),
        "gemini-3.5-flash-lite": ModelPricing(input_1m=0.30, cached_1m=0.03, output_1m=2.50),
        "gemini-3.1-flash-lite": ModelPricing(input_1m=0.25, cached_1m=0.025, output_1m=1.50),
    }

    for provider_id in ("gemini", "antigravity"):
        for model_id, model_pricing in expected.items():
            assert pricing[f"{provider_id}:{model_id}"] == model_pricing


def test_default_pricing_includes_current_copilot_models() -> None:
    pricing = get_default_pricing()
    expected = {
        "gpt-5.6-sol": ModelPricing(input_1m=2.00, cached_1m=0.20, output_1m=10.00),
        "gpt-5.6-terra": ModelPricing(input_1m=2.00, cached_1m=0.20, output_1m=12.00),
        "gpt-5.6-luna": ModelPricing(input_1m=0.20, cached_1m=0.02, output_1m=1.20),
        "claude-opus-5": ModelPricing(input_1m=5.00, cached_1m=0.50, output_1m=25.00),
        "gemini-3.7-flash": ModelPricing(input_1m=0.75, cached_1m=0.075, output_1m=3.75),
        "raptor-mini": ModelPricing(input_1m=0.25, cached_1m=0.025, output_1m=2.00),
        "mai-code-1.1-flash": ModelPricing(input_1m=0.20, cached_1m=0.02, output_1m=1.20),
        "grok-4.6": ModelPricing(input_1m=2.00, cached_1m=0.50, output_1m=6.00),
        "kimi-k3": ModelPricing(input_1m=3.00, cached_1m=0.30, output_1m=15.00),
    }

    for model_id, model_pricing in expected.items():
        assert pricing[f"copilot:{model_id}"] == model_pricing


def test_default_pricing_covers_current_provider_model_catalogs() -> None:
    pricing = get_default_pricing()
    current_models = {
        "codex": {
            "gpt-6-astra",
            "gpt-5.6-sol",
            "gpt-5.6-terra",
            "gpt-5.6-luna",
            "gpt-5.5",
            "gpt-5.5-rosalind",
            "daybreak-blue",
            "daybreak-red",
            "gpt-5.4",
            "gpt-5.4-mini",
            "gpt-5.3-codex",
            "gpt-5.2",
        },
        "claude": {
            "claude-fable-5",
            "claude-mythos-5",
            "claude-opus-5",
            "claude-opus-4-8",
            "claude-sonnet-5",
            "claude-sonnet-4-6",
            "claude-haiku-4-5",
        },
        "gemini": {
            "gemini-3.7-flash",
            "gemini-3.6-flash",
            "gemini-3.5-flash",
            "gemini-3.5-flash-lite",
            "gemini-3.1-pro-preview",
            "gemini-3.1-flash-lite",
        },
        "antigravity": {
            "gemini-3.7-flash",
            "gemini-3.6-flash",
            "gemini-3.5-flash",
            "gemini-3.1-pro",
            "claude-sonnet-4",
            "claude-opus-4.6",
            "gpt-oss",
        },
        "copilot": {
            "gpt-5-mini",
            "gpt-5.3-codex",
            "gpt-5.4",
            "gpt-5.4-mini",
            "gpt-5.4-nano",
            "gpt-5.5",
            "gpt-5.6-luna",
            "gpt-5.6-sol",
            "gpt-5.6-terra",
            "claude-haiku-4-5",
            "claude-opus-4-5",
            "claude-opus-4-6",
            "claude-opus-4-7",
            "claude-opus-4-8",
            "claude-opus-4-8-fast",
            "claude-opus-5",
            "claude-sonnet-4-5",
            "claude-sonnet-4-6",
            "claude-sonnet-5",
            "claude-fable-5",
            "gemini-3.1-pro",
            "gemini-3.5-flash",
            "gemini-3.6-flash",
            "gemini-3.7-flash",
            "raptor-mini",
            "mai-code-1-flash",
            "mai-code-1.1-flash",
            "grok-4.5",
            "grok-4.6",
            "kimi-k2.7-code",
            "kimi-k3",
        },
    }

    for provider_id, model_ids in current_models.items():
        assert {f"{provider_id}:{model_id}" for model_id in model_ids} <= pricing.keys()


def test_default_config_includes_antigravity() -> None:
    config = AppConfig()

    assert config.antigravity.home_path == "~/.gemini/antigravity-cli"


def test_default_pricing_includes_antigravity_gemini_models() -> None:
    pricing = get_default_pricing()

    assert pricing["antigravity:gemini-3-pro-preview"].input_1m == 2.00
    assert pricing["antigravity:gemini-2.5-flash"].output_1m == 2.50
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


def test_load_config_replaces_superseded_defaults_but_preserves_custom_prices(tmp_path) -> None:
    config_path = tmp_path / "config.json"
    saved = AppConfig()
    saved.pricing["codex:gpt-5.6"] = ModelPricing(input_1m=5.00, cached_1m=0.50, output_1m=30.00)
    saved.pricing["gemini:gemini-3.6-flash"] = ModelPricing(
        input_1m=99.00, cached_1m=9.00, output_1m=99.00
    )
    save_config(saved, str(config_path))

    loaded = load_config(str(config_path))

    assert loaded.pricing["codex:gpt-5.6"] == ModelPricing(
        input_1m=4.00, cached_1m=0.40, output_1m=20.00
    )
    assert loaded.pricing["gemini:gemini-3.6-flash"] == ModelPricing(
        input_1m=99.00, cached_1m=9.00, output_1m=99.00
    )
