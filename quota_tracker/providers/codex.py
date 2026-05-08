"""Codex provider implementation."""

from typing import Iterable

from quota_tracker.core.models import QuotaRecord, SessionRecord, TokenUsageRecord
from quota_tracker.providers.base import BaseProvider


class CodexProvider(BaseProvider):
    """Codex provider implementation."""

    @property
    def provider_id(self) -> str:
        return "codex"

    @property
    def display_name(self) -> str:
        return "Codex"

    def scan_passive(self, home_path: str) -> Iterable[SessionRecord | TokenUsageRecord]:
        # Logic from codex_local_audit.py will be moved here in detail
        return []

    def probe_active(self, home_path: str) -> Iterable[QuotaRecord]:
        # Logic from codex_local_audit.py will be moved here in detail
        return []
