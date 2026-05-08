"""Database connection management."""

import sqlite3
from pathlib import Path

from quota_tracker.utils.logging import get_logger

logger = get_logger(__name__)


def get_connection(db_path: Path) -> sqlite3.Connection:
    """
    Get a configured SQLite connection.

    - Enables WAL mode.
    - Enables foreign keys.
    - Sets row factory to sqlite3.Row.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))

    # Enable WAL mode for better concurrency
    conn.execute("PRAGMA journal_mode=WAL")

    # Enable foreign keys
    conn.execute("PRAGMA foreign_keys=ON")

    # Use Row factory for dict-like access
    conn.row_factory = sqlite3.Row

    return conn


class Database:
    """Helper class for database operations."""

    def __init__(self, db_path: Path):
        self.db_path = db_path

    def connect(self) -> sqlite3.Connection:
        """Get a connection to the database."""
        return get_connection(self.db_path)
