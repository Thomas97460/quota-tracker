"""Base provider interface."""

from abc import ABC, abstractmethod
from typing import Iterable

from quota_tracker.core.models import QuotaRecord, SessionRecord, TokenUsageRecord


class BaseProvider(ABC):
    """Abstract base class for all providers."""

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Return the unique provider ID."""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Return the provider display name."""

    @abstractmethod
    def scan_passive(self, home_path: str) -> Iterable[SessionRecord | TokenUsageRecord]:
        """Perform a passive scan of local history."""

    @abstractmethod
    def probe_active(self, home_path: str) -> Iterable[QuotaRecord]:
        """Perform an active quota probe."""
