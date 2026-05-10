"""CRUD helpers built on top of the migrated schema."""

from __future__ import annotations

import json
import sqlite3
from hashlib import sha256
from typing import Any

from quota_tracker.db.records import QuotaRecord, SessionRecord, TokenUsageRecord
from quota_tracker.db.schema import (
    deterministic_session_id,
    ensure_provider,
    utc_now_iso,
    validate_json_text,
)


def upsert_session(conn: sqlite3.Connection, record: SessionRecord) -> str:
    """Upsert a session and return deterministic session id."""

    ensure_provider(record.provider_id)
    session_id = deterministic_session_id(record.provider_id, record.external_session_id)
    metadata_json = validate_json_text(record.metadata)
    conn.execute(
        """
        INSERT INTO sessions(
          id, provider_id, external_session_id, model_name, project_path, project_name,
          created_at, last_seen_at, metadata
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          model_name=excluded.model_name,
          project_path=excluded.project_path,
          project_name=excluded.project_name,
          last_seen_at=excluded.last_seen_at,
          metadata=excluded.metadata
        """,
        (
            session_id,
            record.provider_id,
            record.external_session_id,
            record.model_name,
            record.project_path,
            record.project_name,
            record.created_at,
            record.last_seen_at,
            metadata_json,
        ),
    )
    return session_id


def insert_token_usage(conn: sqlite3.Connection, record: TokenUsageRecord) -> None:
    """Insert token usage row idempotently using unique provider/session/event key."""

    ensure_provider(record.provider_id)
    key = f"{record.provider_id}:{record.session_id}:{record.external_event_id}"
    row_id = sha256(key.encode()).hexdigest()
    conn.execute(
        """
        INSERT INTO token_usage_history(
          id, provider_id, session_id, external_event_id, timestamp, model_name, source,
          input_tokens, output_tokens, cached_tokens, reasoning_tokens, thoughts_tokens,
          tool_tokens, total_tokens, raw_data, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(provider_id, session_id, external_event_id) DO NOTHING
        """,
        (
            row_id,
            record.provider_id,
            record.session_id,
            record.external_event_id,
            record.timestamp,
            record.model_name,
            record.source,
            record.input_tokens,
            record.output_tokens,
            record.cached_tokens,
            record.reasoning_tokens,
            record.thoughts_tokens,
            record.tool_tokens,
            record.total_tokens,
            validate_json_text(record.raw_data),
            utc_now_iso(),
        ),
    )


def insert_quota(conn: sqlite3.Connection, record: QuotaRecord) -> None:
    """Insert a quota history row."""

    ensure_provider(record.provider_id)
    row_id = sha256(
        f"{record.provider_id}:{record.quota_name}:{record.source}:{record.timestamp}".encode()
    ).hexdigest()
    conn.execute(
        """
        INSERT OR REPLACE INTO quota_history(
          id, provider_id, quota_name, source, timestamp, used_percent, remaining_percent,
          window_minutes, resets_at, raw_data, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row_id,
            record.provider_id,
            record.quota_name,
            record.source,
            record.timestamp,
            record.used_percent,
            record.remaining_percent,
            record.window_minutes,
            record.resets_at,
            validate_json_text(record.raw_data),
            utc_now_iso(),
        ),
    )


def list_provider_health(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return provider status summary with sanitized config."""

    rows = conn.execute(
        "SELECT id, enabled, config, updated_at FROM providers ORDER BY id"
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        cfg = json.loads(row["config"])
        safe_cfg = {
            "home_path": cfg.get("home_path"),
            "active_probe_enabled": True,
            "passive_sync_enabled": cfg.get("passive_sync_enabled"),
            "high_water_marks": cfg.get("high_water_marks", {}),
            "safe_options": cfg.get("safe_options", {}),
        }
        out.append(
            {
                "id": row["id"],
                "enabled": bool(row["enabled"]),
                "config": safe_cfg,
                "updated_at": row["updated_at"],
            }
        )
    return out


def get_provider_row(conn: sqlite3.Connection, provider_id: str) -> dict[str, Any] | None:
    """Return one provider row with parsed config, or None if missing."""

    ensure_provider(provider_id)
    row = conn.execute(
        "SELECT id, enabled, config, created_at, updated_at FROM providers WHERE id = ?",
        (provider_id,),
    ).fetchone()
    if row is None:
        return None
    return {
        "id": row["id"],
        "enabled": bool(row["enabled"]),
        "config": json.loads(row["config"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_provider_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return all provider rows with parsed config."""

    rows = conn.execute(
        "SELECT id, enabled, config, created_at, updated_at FROM providers ORDER BY id"
    ).fetchall()
    return [
        {
            "id": row["id"],
            "enabled": bool(row["enabled"]),
            "config": json.loads(row["config"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]


def update_provider_row(
    conn: sqlite3.Connection, provider_id: str, *, enabled: bool, config: dict[str, Any]
) -> None:
    """Update one provider row with sanitized JSON config."""

    ensure_provider(provider_id)
    conn.execute(
        """
        UPDATE providers
        SET enabled = ?, config = ?, updated_at = ?
        WHERE id = ?
        """,
        (1 if enabled else 0, validate_json_text(config), utc_now_iso(), provider_id),
    )
