"""Database migration logic."""

import re
import sqlite3
from pathlib import Path

from quota_tracker.utils.logging import get_logger

logger = get_logger(__name__)


def get_migrations_dir() -> Path:
    """Get the path to the migrations directory."""
    return Path(__file__).parent / "migrations"


def list_migrations() -> list[tuple[int, str, Path]]:
    """
    List all available migration files.
    Returns a list of (version, name, path) tuples sorted by version.
    """
    migrations_dir = get_migrations_dir()
    migrations = []

    if not migrations_dir.exists():
        logger.warning(f"Migrations directory not found: {migrations_dir}")
        return []

    for path in migrations_dir.glob("*.sql"):
        match = re.match(r"(\d+)_(.*)\.sql", path.name)
        if match:
            version = int(match.group(1))
            name = match.group(2)
            migrations.append((version, name, path))

    return sorted(migrations, key=lambda x: x[0])


def ensure_migration_table(conn: sqlite3.Connection) -> None:
    """Ensure the schema_migrations table exists."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        )
        """
    )
    conn.commit()


def get_applied_versions(conn: sqlite3.Connection) -> list[int]:
    """Get the list of applied migration versions."""
    cursor = conn.execute("SELECT version FROM schema_migrations ORDER BY version")
    return [row["version"] for row in cursor.fetchall()]


def apply_migrations(conn: sqlite3.Connection) -> None:
    """Apply all pending migrations."""
    ensure_migration_table(conn)
    applied = get_applied_versions(conn)
    available = list_migrations()

    for version, name, path in available:
        if version not in applied:
            logger.info(f"Applying migration {version}_{name}...")
            sql = path.read_text(encoding="utf-8")

            try:
                # Use executescript to run multiple statements
                # It automatically starts a transaction but doesn't commit it?
                # Actually, executescript issues a BEGIN and runs the SQL.
                # We should be careful about transaction management here.
                conn.executescript(sql)

                # Record migration
                conn.execute(
                    "INSERT INTO schema_migrations (version, name) VALUES (?, ?)",
                    (version, name),
                )
                conn.commit()
                logger.info(f"Successfully applied migration {version}_{name}")
            except Exception as e:
                conn.rollback()
                logger.error(f"Failed to apply migration {version}_{name}: {e}")
                raise
        else:
            logger.debug(f"Migration {version}_{name} already applied")
