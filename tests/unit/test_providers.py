"""Unit tests for provider base and specific implementations."""

from collections.abc import Iterable
from typing import Any

from quota_tracker.core.models import QuotaRecord, SessionRecord, TokenUsageRecord
from quota_tracker.providers.base import BaseProvider
from quota_tracker.providers.codex import CodexProvider
from quota_tracker.providers.copilot import CopilotProvider
from quota_tracker.providers.gemini import GeminiProvider


def test_base_provider_interface() -> None:
    """Test that a concrete implementation of BaseProvider works."""

    class MockProvider(BaseProvider):
        @property
        def provider_id(self) -> str:
            return "mock"

        @property
        def display_name(self) -> str:
            return "Mock Provider"

        @property
        def default_home_path(self) -> str:
            return "/tmp/mock"

        @property
        def supports_active_probe(self) -> bool:
            return True

        @property
        def supports_passive_sync(self) -> bool:
            return True

        def scan_passive(
            self, _home_path: str
        ) -> Iterable[SessionRecord | TokenUsageRecord]:
            return []

        def scan_incremental(
            self, _home_path: str, _sync_state: dict[str, Any]
        ) -> Iterable[SessionRecord | TokenUsageRecord]:
            return []

        def probe_active(self, _home_path: str) -> Iterable[QuotaRecord]:
            return []

    provider = MockProvider()
    assert provider.provider_id == "mock"
    assert provider.display_name == "Mock Provider"
    assert provider.default_home_path == "/tmp/mock"
    assert provider.supports_active_probe is True
    assert provider.supports_passive_sync is True


def test_provider_stubs() -> None:
    """Test that provider stubs implement the interface correctly."""
    providers = [GeminiProvider(), CodexProvider(), CopilotProvider()]
    for provider in providers:
        assert isinstance(provider, BaseProvider)
        assert provider.provider_id in ["gemini", "codex", "copilot"]
        assert provider.display_name in ["Gemini", "Codex", "Copilot"]
        assert provider.default_home_path.startswith("~/")
        assert provider.supports_active_probe is True
        assert provider.supports_passive_sync is True
        assert list(provider.scan_passive("/tmp")) == []
        assert list(provider.scan_incremental("/tmp", {})) == []
        assert list(provider.probe_active("/tmp")) == []
