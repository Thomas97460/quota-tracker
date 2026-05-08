"""Base provider interface."""

from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import Any

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

    @property
    @abstractmethod
    def default_home_path(self) -> str:
        """Return the default home path for the provider."""

    @property
    @abstractmethod
    def supports_active_probe(self) -> bool:
        """Return True if the provider supports active quota probing."""

    @property
    @abstractmethod
    def supports_passive_sync(self) -> bool:
        """Return True if the provider supports passive history syncing."""

    @abstractmethod
    def scan_passive(
        self, home_path: str
    ) -> Iterable[SessionRecord | TokenUsageRecord]:
        """Perform a full passive scan of local history."""

    @abstractmethod
    def scan_incremental(
        self, home_path: str, sync_state: dict[str, Any]
    ) -> Iterable[SessionRecord | TokenUsageRecord]:
        """Perform an incremental passive scan of local history."""

    @abstractmethod
    def probe_active(self, home_path: str) -> Iterable[QuotaRecord]:
        """Perform an active quota probe."""
