"""Database schema initialization for usage records."""

import sqlite3
from pathlib import Path
from typing import Final

# Default location according to ROADMAP.md
DB_DIR: Final[Path] = Path.home() / ".local" / "share" / "quota-tracker"
DB_PATH: Final[Path] = DB_DIR / "quota-tracker.sqlite3"


def get_connection() -> sqlite3.Connection:
    """Return a connection to the SQLite database."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn: sqlite3.Connection = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def initialize_database() -> None:
    """Initialize the database schema and apply pending migrations."""
    conn: sqlite3.Connection = get_connection()
    cursor: sqlite3.Cursor = conn.cursor()

    # Migration tracking table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Providers table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS providers (
            id TEXT PRIMARY KEY,
            enabled BOOLEAN NOT NULL DEFAULT 1,
            config TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Quota history table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS quota_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider_id TEXT NOT NULL,
            quota_name TEXT NOT NULL,
            source TEXT NOT NULL,
            timestamp TIMESTAMP NOT NULL,
            used_percent REAL,
            remaining_percent REAL,
            window_minutes INTEGER,
            resets_at TIMESTAMP,
            raw_data TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (provider_id) REFERENCES providers (id)
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_quota_provider "
        "ON quota_history (provider_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_quota_timestamp "
        "ON quota_history (timestamp)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_quota_name "
        "ON quota_history (quota_name)"
    )

    # Sessions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            provider_id TEXT NOT NULL,
            external_session_id TEXT NOT NULL,
            model_name TEXT NOT NULL,
            project_path TEXT,
            project_name TEXT,
            metadata TEXT,
            created_at TIMESTAMP NOT NULL,
            last_seen_at TIMESTAMP NOT NULL,
            FOREIGN KEY (provider_id) REFERENCES providers (id)
        )
    """)

    # Token usage history table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS token_usage_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            external_event_id TEXT NOT NULL,
            timestamp TIMESTAMP NOT NULL,
            model_name TEXT NOT NULL,
            source TEXT NOT NULL,
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            cached_tokens INTEGER DEFAULT 0,
            reasoning_tokens INTEGER DEFAULT 0,
            thoughts_tokens INTEGER DEFAULT 0,
            tool_tokens INTEGER DEFAULT 0,
            total_tokens INTEGER DEFAULT 0,
            raw_data TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(provider_id, session_id, external_event_id),
            FOREIGN KEY (provider_id) REFERENCES providers (id),
            FOREIGN KEY (session_id) REFERENCES sessions (id)
        )
    """)

    conn.commit()
    conn.close()


if __name__ == "__main__":
    initialize_database()
    print("Database initialized.")
