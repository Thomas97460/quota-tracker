"""Database schema initialization for usage records."""

import sqlite3
from pathlib import Path

DB_PATH: Path = Path("data/quota.db")


def get_connection() -> sqlite3.Connection:
    """Return a connection to the SQLite database."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn: sqlite3.Connection = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize_database() -> None:
    """Initialize the database schema if it does not exist."""
    conn: sqlite3.Connection = get_connection()
    cursor: sqlite3.Cursor = conn.cursor()

    # Common schema for copilot/codex data
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usage_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            tokens_used INTEGER NOT NULL,
            session_id TEXT,
            metadata TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS migration_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version INTEGER NOT NULL,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


if __name__ == "__main__":
    initialize_database()
    print("Database initialized.")
