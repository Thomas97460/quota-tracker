"""Database repositories for quota-tracker."""

import json
from datetime import UTC, datetime
from typing import Any

from quota_tracker.core.models import QuotaRecord, SessionRecord, TokenUsageRecord
from quota_tracker.database.connection import Database


def to_iso(dt: datetime | None) -> str | None:
    """Convert datetime to ISO 8601 string."""
    if dt is None:
        return None
    # Ensure it's UTC and format with Z
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def from_iso(s: str | None) -> datetime | None:
    """Parse ISO 8601 string to datetime."""
    if s is None:
        return None
    try:
        # datetime.fromisoformat handles Z in 3.11+
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt.astimezone(UTC)
    except ValueError:
        return None


class ProviderRepository:
    """Repository for providers table."""

    def __init__(self, db: Database):
        self.db = db

    def initialize_default_providers(self) -> None:
        """Create default provider rows if they don't exist."""
        default_providers = ["gemini", "codex", "copilot"]
        now = to_iso(datetime.now(UTC))

        with self.db.connect() as conn:
            for pid in default_providers:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO providers (
                        id, enabled, config, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (pid, 1, json.dumps({}), now, now)
                )
            conn.commit()


    def get_provider_config(self, provider_id: str) -> dict[str, Any] | None:
        """Get the configuration for a provider."""
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT config FROM providers WHERE id = ?", (provider_id,)
            ).fetchone()
            if row:
                config = json.loads(row["config"])
                if isinstance(config, dict):
                    return config
        return None


class QuotaRepository:
    """Repository for quota_history table."""

    def __init__(self, db: Database):
        self.db = db

    def add_quota_record(self, record: QuotaRecord) -> None:
        """Add a quota record to the database."""
        now = to_iso(datetime.now(UTC))
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO quota_history (
                    provider_id, quota_name, timestamp, used_percent, 
                    remaining_percent, window_minutes, resets_at, 
                    source, raw_data, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.provider_id,
                    record.quota_name,
                    to_iso(record.timestamp),
                    record.used_percent,
                    record.remaining_percent,
                    record.window_minutes,
                    to_iso(record.resets_at),
                    record.source,
                    json.dumps(record.raw_data),
                    now,
                ),
            )
            conn.commit()


class SessionRepository:
    """Repository for sessions table."""

    def __init__(self, db: Database):
        self.db = db

    def upsert_session(self, record: SessionRecord) -> str:
        """
        Upsert a session record.
        Returns the session ID.
        """
        session_id = f"{record.provider_id}:{record.external_session_id}"

        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions (
                    id, provider_id, external_session_id, model_name,
                    project_path, project_name, created_at, last_seen_at, metadata
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    model_name = excluded.model_name,
                    project_path = excluded.project_path,
                    project_name = excluded.project_name,
                    last_seen_at = excluded.last_seen_at,
                    metadata = excluded.metadata
                """,
                (
                    session_id,
                    record.provider_id,
                    record.external_session_id,
                    record.model_name,
                    record.project_path,
                    record.project_name,
                    to_iso(record.created_at or datetime.now(UTC)),
                    to_iso(record.last_seen_at or datetime.now(UTC)),
                    json.dumps(record.metadata),
                ),
            )
            conn.commit()
        return session_id


class TokenUsageRepository:
    """Repository for token_usage_history table."""

    def __init__(self, db: Database):
        self.db = db

    def add_token_usage(self, record: TokenUsageRecord) -> None:
        """Add a token usage record."""
        session_id = f"{record.provider_id}:{record.external_session_id}"
        now = to_iso(datetime.now(UTC))

        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO token_usage_history (
                    session_id, provider_id, external_event_id, timestamp,
                    model_name, input_tokens, output_tokens, cached_tokens,
                    reasoning_tokens, thoughts_tokens, tool_tokens, total_tokens,
                    source, raw_data, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    record.provider_id,
                    record.external_event_id,
                    to_iso(record.timestamp),
                    record.model_name,
                    record.input_tokens,
                    record.output_tokens,
                    record.cached_tokens,
                    record.reasoning_tokens,
                    record.thoughts_tokens,
                    record.tool_tokens,
                    record.total_tokens,
                    "passive_sync",  # Default for now
                    json.dumps(record.raw_data),
                    now,
                ),
            )
            conn.commit()
