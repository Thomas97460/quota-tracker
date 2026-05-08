"""Copilot provider implementation."""

from typing import Iterable

from quota_tracker.core.models import QuotaRecord, SessionRecord, TokenUsageRecord
from quota_tracker.providers.base import BaseProvider


class CopilotProvider(BaseProvider):
    """Copilot provider implementation."""

    @property
    def provider_id(self) -> str:
        return "copilot"

    @property
    def display_name(self) -> str:
        return "Copilot"

    def scan_passive(self, home_path: str) -> Iterable[SessionRecord | TokenUsageRecord]:
        # Logic from copilot_local_audit.py will be moved here in detail
        return []

    def probe_active(self, home_path: str) -> Iterable[QuotaRecord]:
        # Logic from copilot_local_audit.py will be moved here in detail
        return []
