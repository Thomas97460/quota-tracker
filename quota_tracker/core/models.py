"""Core data models for quota_tracker."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class QuotaRecord:
    """Normalized quota record."""

    provider_id: str
    quota_name: str
    timestamp: datetime
    used_percent: float | None
    remaining_percent: float | None
    window_minutes: int | None
    resets_at: datetime | None
    source: str
    raw_data: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Normalize used/remaining percentages."""
        if self.used_percent is None and self.remaining_percent is not None:
            self.used_percent = 100.0 - self.remaining_percent
        elif self.remaining_percent is None and self.used_percent is not None:
            self.remaining_percent = 100.0 - self.used_percent

        if self.used_percent is not None:
            self.used_percent = max(0.0, min(100.0, self.used_percent))
        if self.remaining_percent is not None:
            self.remaining_percent = max(0.0, min(100.0, self.remaining_percent))


@dataclass
class SessionRecord:
    """Normalized session record."""

    provider_id: str
    external_session_id: str
    model_name: str = "unknown"
    project_path: str | None = None
    project_name: str | None = None
    created_at: datetime | None = None
    last_seen_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TokenUsageRecord:
    """Normalized token usage record."""

    provider_id: str
    external_session_id: str
    external_event_id: str
    timestamp: datetime
    model_name: str
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    reasoning_tokens: int = 0
    thoughts_tokens: int = 0
    tool_tokens: int = 0
    total_tokens: int = 0
    raw_data: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Compute total_tokens if not provided."""
        if self.total_tokens == 0:
            self.total_tokens = (
                self.input_tokens
                + self.output_tokens
                + self.cached_tokens
                + self.reasoning_tokens
                + self.thoughts_tokens
                + self.tool_tokens
            )


@dataclass
class FileHighWaterMark:
    """High-water mark for a file-based source."""

    path: str
    size: int
    mtime: float
    last_offset: int = 0
    last_event_timestamp: datetime | None = None


@dataclass
class SQLiteHighWaterMark:
    """High-water mark for a SQLite-based source."""

    database_path: str
    last_row_id: int | None = None
    last_timestamp: datetime | None = None


@dataclass
class ProbeHighWaterMark:
    """High-water mark for an active quota probe."""

    last_success_timestamp: datetime
    quota_name: str
