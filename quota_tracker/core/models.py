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
