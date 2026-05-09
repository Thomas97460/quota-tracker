"""Normalized record dataclasses persisted by the DB layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SessionRecord:
    """Normalized session row input."""

    provider_id: str
    external_session_id: str
    model_name: str
    project_path: str | None
    project_name: str | None
    created_at: str
    last_seen_at: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class TokenUsageRecord:
    """Normalized token usage row input."""

    provider_id: str
    session_id: str
    external_event_id: str
    timestamp: str
    model_name: str
    source: str
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    reasoning_tokens: int
    thoughts_tokens: int
    tool_tokens: int
    total_tokens: int
    raw_data: dict[str, Any]


@dataclass(frozen=True)
class QuotaRecord:
    """Normalized quota row input."""

    provider_id: str
    quota_name: str
    source: str
    timestamp: str
    used_percent: float | None
    remaining_percent: float | None
    window_minutes: int | None
    resets_at: str | None
    raw_data: dict[str, Any]
