"""Provider contract, results, and shared normalization helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from quota_tracker.db import QuotaRecord, SessionRecord


@dataclass(frozen=True)
class ProviderMetadata:
    """Provider capability metadata."""

    id: str
    display_name: str
    default_home_path: str
    supports_active_probe: bool
    supports_passive_sync: bool


@dataclass(frozen=True)
class PassiveSyncResult:
    """Normalized passive sync output."""

    sessions: list[SessionRecord]
    token_usage: list[dict[str, Any]]
    quotas: list[QuotaRecord]
    high_water_marks: dict[str, Any]
    parse_failures: int


class Provider(Protocol):
    """Common provider contract."""

    metadata: ProviderMetadata

    def passive_scan_full(self) -> PassiveSyncResult:
        """Run a full passive scan."""
        ...

    def passive_scan_incremental(self, high_water_marks: dict[str, Any]) -> PassiveSyncResult:
        """Run an incremental passive scan from high-water marks."""
        ...

    def active_probe(self) -> list[QuotaRecord]:
        """Run an active quota probe."""
        ...


def _iso(value: str | None) -> str:
    """Return provided timestamp or current UTC timestamp."""

    if value:
        return value
    return datetime.now(UTC).isoformat()


def normalize_session(
    provider_id: str,
    external_session_id: str,
    model_name: str | None,
    project_path: str | None,
    project_name: str | None,
    created_at: str | None,
    last_seen_at: str | None,
    metadata: dict[str, Any],
) -> SessionRecord:
    """Normalize a session record to the common shape."""

    return SessionRecord(
        provider_id=provider_id,
        external_session_id=external_session_id,
        model_name=model_name or "unknown",
        project_path=project_path,
        project_name=project_name,
        created_at=_iso(created_at),
        last_seen_at=_iso(last_seen_at),
        metadata=metadata,
    )


def normalize_token_usage(
    provider_id: str,
    external_session_id: str,
    external_event_id: str,
    timestamp: str,
    model_name: str | None,
    raw_metadata: dict[str, Any],
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    cached_tokens: int | None = None,
    reasoning_tokens: int | None = None,
    thoughts_tokens: int | None = None,
    tool_tokens: int | None = None,
    total_tokens: int | None = None,
    source: str = "local_log",
) -> dict[str, Any]:
    """Normalize token usage fields and fill absent counts with zero."""

    i = input_tokens or 0
    o = output_tokens or 0
    c = cached_tokens or 0
    r = reasoning_tokens or 0
    th = thoughts_tokens or 0
    tl = tool_tokens or 0
    t = total_tokens if total_tokens is not None else i + o + c + r + th + tl
    return {
        "provider_id": provider_id,
        "external_session_id": external_session_id,
        "external_event_id": external_event_id,
        "timestamp": timestamp,
        "model_name": model_name or "unknown",
        "input_tokens": i,
        "output_tokens": o,
        "cached_tokens": c,
        "reasoning_tokens": r,
        "thoughts_tokens": th,
        "tool_tokens": tl,
        "total_tokens": t,
        "raw_metadata": raw_metadata,
        "source": source,
    }


def _clamp_percent(value: float) -> float:
    """Clamp a percentage value to the inclusive [0, 100] range."""

    return max(0.0, min(100.0, value))


def normalize_quota(
    provider_id: str,
    quota_name: str,
    timestamp: str,
    source: str,
    raw_metadata: dict[str, Any],
    used_percent: float | None = None,
    remaining_percent: float | None = None,
    window_minutes: int | None = None,
    resets_at: str | None = None,
) -> QuotaRecord:
    """Normalize quota percentages and clamp in [0, 100]."""

    used = used_percent
    remaining = remaining_percent
    if used is None and remaining is not None:
        used = 100.0 - remaining
    if remaining is None and used is not None:
        remaining = 100.0 - used
    if used is not None:
        used = _clamp_percent(float(used))
    if remaining is not None:
        remaining = _clamp_percent(float(remaining))
    return QuotaRecord(
        provider_id=provider_id,
        quota_name=quota_name,
        source=source,
        timestamp=timestamp,
        used_percent=used,
        remaining_percent=remaining,
        window_minutes=window_minutes,
        resets_at=resets_at,
        raw_data=raw_metadata,
    )
