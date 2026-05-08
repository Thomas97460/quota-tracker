"""Copilot provider implementation."""

from collections.abc import Iterable
from typing import Any

from quota_tracker.core.models import QuotaRecord, SessionRecord, TokenUsageRecord
from quota_tracker.providers.base import BaseProvider


class CopilotProvider(BaseProvider):
    """Copilot provider implementation."""

    @property
    def provider_id(self) -> str:
        """Return the unique identifier for the provider."""
        return "copilot"

    @property
    def display_name(self) -> str:
        """Return the human-readable name of the provider."""
        return "Copilot"

    @property
    def default_home_path(self) -> str:
        """Return the default home path for the provider."""
        return "~/.copilot"

    @property
    def supports_active_probe(self) -> bool:
        """Return True if the provider supports active quota probing."""
        return True

    @property
    def supports_passive_sync(self) -> bool:
        """Return True if the provider supports passive history syncing."""
        return True

    def scan_passive(
        self, _home_path: str
    ) -> Iterable[SessionRecord | TokenUsageRecord | QuotaRecord]:
        """Perform a full passive scan of local history."""
        # Logic from copilot_local_audit.py will be moved here in detail
        return []

    def scan_incremental(
        self, _home_path: str, _sync_state: dict[str, Any]
    ) -> Iterable[SessionRecord | TokenUsageRecord | QuotaRecord]:
        """Perform an incremental passive scan of local history."""
        return []

    def probe_active(self, _home_path: str) -> Iterable[QuotaRecord]:
        """Perform an active quota probe."""
        # Logic from copilot_local_audit.py will be moved here in detail
        return []
