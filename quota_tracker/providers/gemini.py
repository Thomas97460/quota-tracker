"""Gemini provider implementation."""

from typing import Iterable

from quota_tracker.core.models import QuotaRecord, SessionRecord, TokenUsageRecord
from quota_tracker.providers.base import BaseProvider


class GeminiProvider(BaseProvider):
    """Gemini provider implementation."""

    @property
    def provider_id(self) -> str:
        return "gemini"

    @property
    def display_name(self) -> str:
        return "Gemini"

    def scan_passive(self, home_path: str) -> Iterable[SessionRecord | TokenUsageRecord]:
        # Logic from gemini_local_audit.py will be moved here in detail
        return []

    def probe_active(self, home_path: str) -> Iterable[QuotaRecord]:
        # Logic from gemini_local_audit.py will be moved here in detail
        return []
