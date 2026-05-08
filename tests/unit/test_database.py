"""Unit tests for database and migrations."""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from quota_tracker.database import Database, apply_migrations


def test_database_connection() -> None:
    """Test that we can connect to a database and WAL mode is enabled."""
    with tempfile.NamedTemporaryFile() as tmp:
        db_path = Path(tmp.name)
        db = Database(db_path)
        conn = db.connect()

        # Check WAL mode
        cursor = conn.execute("PRAGMA journal_mode")
        assert cursor.fetchone()[0] == "wal"

        # Check foreign keys
        cursor = conn.execute("PRAGMA foreign_keys")
        assert cursor.fetchone()[0] == 1

        conn.close()


def test_apply_migrations() -> None:
    """Test that migrations are applied correctly and idempotently."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test.sqlite3"
        db = Database(db_path)

        # First application
        conn = db.connect()
        apply_migrations(conn)

        # Check that tables exist
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row["name"] for row in cursor.fetchall()}
        assert "schema_migrations" in tables
        assert "providers" in tables
        assert "quota_history" in tables
        assert "sessions" in tables
        assert "token_usage_history" in tables

        # Check version
        cursor = conn.execute("SELECT version FROM schema_migrations")
        assert cursor.fetchone()["version"] == 1

        conn.close()

        # Second application (idempotency)
        conn = db.connect()
        apply_migrations(conn)

        # Still version 1
        cursor = conn.execute("SELECT version FROM schema_migrations")
        rows = cursor.fetchall()
        assert len(rows) == 1
        assert rows[0]["version"] == 1

        conn.close()


def test_provider_id_constraint() -> None:
    """Test the provider ID check constraint."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test.sqlite3"
        db = Database(db_path)
        conn = db.connect()
        apply_migrations(conn)

        # Valid provider
        conn.execute(
            """
            INSERT INTO providers (id, config, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            ("gemini", "{}", "2024-01-01T00:00:00Z", "2024-01-01T00:00:00Z"),
        )
        conn.commit()

        # Invalid provider
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO providers (id, config, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                ("invalid", "{}", "2024-01-01T00:00:00Z", "2024-01-01T00:00:00Z"),
            )

        conn.close()


def test_provider_repository_initialization() -> None:
    """Test that default providers are initialized correctly."""
    from quota_tracker.database.repositories import ProviderRepository

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test.sqlite3"
        db = Database(db_path)
        conn = db.connect()
        apply_migrations(conn)
        conn.close()

        repo = ProviderRepository(db)
        repo.initialize_default_providers()

        with db.connect() as conn:
            cursor = conn.execute("SELECT id FROM providers")
            providers = {row["id"] for row in cursor.fetchall()}
            assert providers == {"gemini", "codex", "copilot"}


def test_session_repository_upsert() -> None:
    """Test session upsert logic."""
    from datetime import datetime

    from quota_tracker.core.models import SessionRecord
    from quota_tracker.database.repositories import SessionRepository

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test.sqlite3"
        db = Database(db_path)
        conn = db.connect()
        apply_migrations(conn)
        # Add provider first due to foreign key
        conn.execute(
            """
            INSERT INTO providers (id, config, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            ("gemini", "{}", "2024-01-01T00:00:00Z", "2024-01-01T00:00:00Z"),
        )
        conn.commit()
        conn.close()

        repo = SessionRepository(db)
        record = SessionRecord(
            provider_id="gemini",
            external_session_id="session-123",
            model_name="gemini-pro",
            created_at=datetime(2024, 1, 1),
            last_seen_at=datetime(2024, 1, 1),
            metadata={"version": "1.0"},
        )

        session_id = repo.upsert_session(record)
        assert session_id == "gemini:session-123"

        with db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            assert row["model_name"] == "gemini-pro"
            assert row["external_session_id"] == "session-123"

        # Update session
        record.model_name = "gemini-ultra"
        repo.upsert_session(record)

        with db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            assert row["model_name"] == "gemini-ultra"
