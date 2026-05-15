"""SQLite connection, migrations, and shared helpers."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

PROVIDERS = ("gemini", "codex", "copilot", "claude")


def utc_now_iso() -> str:
    """Return current UTC timestamp as ISO 8601 string."""

    return datetime.now(UTC).isoformat()


def deterministic_session_id(provider_id: str, external_session_id: str) -> str:
    """Build deterministic session id from provider and external session id."""

    key = f"{provider_id}:{external_session_id}".encode()
    return sha256(key).hexdigest()


def validate_json_text(value: dict[str, Any]) -> str:
    """Validate object is JSON-serializable and return compact JSON text."""

    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))


def ensure_provider(provider_id: str) -> None:
    """Validate provider id belongs to the supported provider set."""

    if provider_id not in PROVIDERS:
        raise ValueError(f"unsupported provider_id: {provider_id}")


def connect_db(db_path: str) -> sqlite3.Connection:
    """Open SQLite connection with safe defaults and WAL mode."""

    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


def apply_migrations(conn: sqlite3.Connection) -> list[str]:
    """Apply idempotent schema migrations. Returns IDs of newly-applied migrations."""

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
          id TEXT PRIMARY KEY,
          applied_at TEXT NOT NULL
        )
        """
    )

    migrations: list[tuple[str, str]] = [
        (
            "0001_initial",
            """
            CREATE TABLE IF NOT EXISTS providers (
              id TEXT PRIMARY KEY CHECK (id IN ('gemini', 'codex', 'copilot')),
              enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
              config TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS quota_history (
              id TEXT PRIMARY KEY,
              provider_id TEXT NOT NULL,
              quota_name TEXT NOT NULL,
              source TEXT NOT NULL,
              timestamp TEXT NOT NULL,
              used_percent REAL,
              remaining_percent REAL,
              window_minutes INTEGER,
              resets_at TEXT,
              raw_data TEXT NOT NULL,
              created_at TEXT NOT NULL,
              FOREIGN KEY (provider_id) REFERENCES providers(id)
            );
            CREATE INDEX IF NOT EXISTS idx_quota_history_provider_id ON quota_history(provider_id);
            CREATE INDEX IF NOT EXISTS idx_quota_history_timestamp ON quota_history(timestamp);
            CREATE INDEX IF NOT EXISTS idx_quota_history_quota_name ON quota_history(quota_name);
            CREATE INDEX IF NOT EXISTS idx_quota_history_resets_at ON quota_history(resets_at);
            """,
        ),
        (
            "0002_sessions_table",
            """
            CREATE TABLE IF NOT EXISTS sessions (
              id TEXT PRIMARY KEY,
              provider_id TEXT NOT NULL,
              external_session_id TEXT NOT NULL,
              model_name TEXT NOT NULL,
              project_path TEXT,
              project_name TEXT,
              created_at TEXT NOT NULL,
              last_seen_at TEXT NOT NULL,
              metadata TEXT NOT NULL,
              FOREIGN KEY (provider_id) REFERENCES providers(id)
            );

            CREATE TABLE IF NOT EXISTS token_usage_history (
              id TEXT PRIMARY KEY,
              provider_id TEXT NOT NULL,
              session_id TEXT NOT NULL,
              external_event_id TEXT NOT NULL,
              timestamp TEXT NOT NULL,
              model_name TEXT NOT NULL,
              source TEXT NOT NULL,
              input_tokens INTEGER NOT NULL,
              output_tokens INTEGER NOT NULL,
              cached_tokens INTEGER NOT NULL,
              reasoning_tokens INTEGER NOT NULL,
              thoughts_tokens INTEGER NOT NULL,
              tool_tokens INTEGER NOT NULL,
              total_tokens INTEGER NOT NULL,
              raw_data TEXT NOT NULL,
              created_at TEXT NOT NULL,
              FOREIGN KEY (provider_id) REFERENCES providers(id),
              FOREIGN KEY (session_id) REFERENCES sessions(id),
              UNIQUE(provider_id, session_id, external_event_id)
            );

            CREATE TABLE IF NOT EXISTS maintenance_events (
              id TEXT PRIMARY KEY,
              operation TEXT NOT NULL,
              timestamp TEXT NOT NULL,
              metadata TEXT NOT NULL
            );
            """,
        ),
        (
            "0003_providers_drop_id_check",
            """
            PRAGMA foreign_keys = OFF;
            CREATE TABLE IF NOT EXISTS providers_new (
              id TEXT PRIMARY KEY,
              enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
              config TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            INSERT OR IGNORE INTO providers_new SELECT * FROM providers;
            DROP TABLE IF EXISTS providers;
            ALTER TABLE providers_new RENAME TO providers;
            PRAGMA foreign_keys = ON;
            """,
        ),
        (
            "0003_fix_double_counted_cached_tokens",
            """
            UPDATE token_usage_history 
            SET input_tokens = MAX(0, input_tokens - cached_tokens)
            WHERE cached_tokens > 0;
            """,
        ),
        (
            "0004_fix_total_tokens_deduplication",
            """
            UPDATE token_usage_history 
            SET total_tokens = input_tokens + output_tokens + cached_tokens + 
                               reasoning_tokens + thoughts_tokens + tool_tokens;
            """,
        ),
        (
            "0005_quota_history_archived_table",
            """
            CREATE TABLE IF NOT EXISTS quota_history_archived (
              id TEXT PRIMARY KEY,
              provider_id TEXT NOT NULL,
              quota_name TEXT NOT NULL,
              timestamp TEXT NOT NULL,
              used_percent REAL,
              remaining_percent REAL,
              window_minutes INTEGER,
              point_count INTEGER NOT NULL,
              FOREIGN KEY (provider_id) REFERENCES providers(id)
            );
            CREATE INDEX IF NOT EXISTS idx_quota_archived_provider 
              ON quota_history_archived(provider_id);
            CREATE INDEX IF NOT EXISTS idx_quota_archived_timestamp 
              ON quota_history_archived(timestamp);
            """,
        ),
        (
            "0006_quota_history_archival_policy",
            """
            -- Move records older than 30 days to the archive table, aggregated by hour (3600s).
            INSERT INTO quota_history_archived (
                id, provider_id, quota_name, timestamp, 
                used_percent, remaining_percent, window_minutes, point_count
            )
            SELECT 
                provider_id || ':' || quota_name || ':' || (unixepoch(timestamp) / 3600),
                provider_id, 
                quota_name,
                datetime((unixepoch(timestamp) / 3600) * 3600, 'unixepoch'),
                AVG(used_percent),
                AVG(remaining_percent),
                MAX(window_minutes),
                COUNT(*)
            FROM quota_history 
            WHERE datetime(timestamp) < datetime('now', '-30 days')
            GROUP BY provider_id, quota_name, (unixepoch(timestamp) / 3600)
            ON CONFLICT(id) DO UPDATE SET
                used_percent = (
                    quota_history_archived.used_percent * quota_history_archived.point_count + 
                    excluded.used_percent * excluded.point_count
                ) / (quota_history_archived.point_count + excluded.point_count),
                point_count = quota_history_archived.point_count + excluded.point_count;

            -- Delete the original high-resolution records after archival.
            DELETE FROM quota_history WHERE datetime(timestamp) < datetime('now', '-30 days');
            """,
        ),
    ]

    newly_applied: list[str] = []
    for migration_id, sql in migrations:
        present = conn.execute(
            "SELECT 1 FROM schema_migrations WHERE id = ?", (migration_id,)
        ).fetchone()
        if present:
            continue
        conn.executescript(sql)
        conn.execute(
            "INSERT INTO schema_migrations(id, applied_at) VALUES(?, ?)",
            (migration_id, utc_now_iso()),
        )
        newly_applied.append(migration_id)

    _ensure_default_providers(conn)
    conn.commit()
    return newly_applied


def _ensure_default_providers(conn: sqlite3.Connection) -> None:
    """Insert default provider rows when missing."""

    now = utc_now_iso()
    for provider in PROVIDERS:
        default_config = {
            "home_path": f"~/.{provider}",
            "active_probe_enabled": True,
            "high_water_marks": {},
            "safe_options": {},
        }
        conn.execute(
            """
            INSERT INTO providers(id, enabled, config, created_at, updated_at)
            VALUES(?, 1, ?, ?, ?)
            ON CONFLICT(id) DO NOTHING
            """,
            (provider, validate_json_text(default_config), now, now),
        )
        row = conn.execute("SELECT config FROM providers WHERE id = ?", (provider,)).fetchone()
        if row is None:
            continue
        config = json.loads(row["config"])
        if config.get("active_probe_enabled") is not True:
            config["active_probe_enabled"] = True
            conn.execute(
                "UPDATE providers SET config = ?, updated_at = ? WHERE id = ?",
                (validate_json_text(config), now, provider),
            )


@contextmanager
def write_transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Run a provider sync write batch in one transaction."""

    conn.execute("BEGIN")
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    else:
        conn.commit()
