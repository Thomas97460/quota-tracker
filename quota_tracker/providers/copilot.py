"""Copilot provider implementation."""

from collections.abc import Iterable

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

    def scan_passive(
        self, _home_path: str
    ) -> Iterable[SessionRecord | TokenUsageRecord]:
        """Scan the local environment for session and usage data."""
        # Logic from copilot_local_audit.py will be moved here in detail
        return []

    def probe_active(self, _home_path: str) -> Iterable[QuotaRecord]:
        """Probe the provider API for current quota status."""
        # Logic from copilot_local_audit.py will be moved here in detail
        return []
