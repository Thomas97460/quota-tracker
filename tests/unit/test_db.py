"""Unit tests for DB layer."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from quota_tracker.db import (
    QuotaRecord,
    SessionRecord,
    TokenUsageRecord,
    apply_migrations,
    connect_db,
    deterministic_session_id,
    get_provider_row,
    insert_quota,
    insert_token_usage,
    list_provider_health,
    list_provider_rows,
    update_provider_row,
    upsert_session,
    validate_json_text,
    write_transaction,
)


def _db(tmp_path: Path) -> sqlite3.Connection:
    return connect_db(str(tmp_path / "test.sqlite3"))


def test_validate_json_text() -> None:
    assert validate_json_text({"a": 1}) == '{"a":1}'


def test_deterministic_session_id_stable() -> None:
    first = deterministic_session_id("codex", "s1")
    second = deterministic_session_id("codex", "s1")
    third = deterministic_session_id("codex", "s2")
    assert first == second
    assert first != third


def test_migrations_idempotent_and_default_providers(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    try:
        apply_migrations(conn)
        before = conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
        providers = conn.execute("SELECT id FROM providers ORDER BY id").fetchall()
        assert [r[0] for r in providers] == ["claude", "codex", "copilot", "gemini"]
        apply_migrations(conn)
        after = conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
        assert before == after == 2
    finally:
        conn.close()


def test_wal_enabled(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    try:
        mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
        assert str(mode).lower() == "wal"
    finally:
        conn.close()


def test_upsert_session_and_token_usage_idempotent(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    try:
        apply_migrations(conn)
        sess = SessionRecord(
            provider_id="codex",
            external_session_id="ext-1",
            model_name="gpt-5",
            project_path="/tmp/p",
            project_name="p",
            created_at="2026-01-01T00:00:00+00:00",
            last_seen_at="2026-01-01T00:10:00+00:00",
            metadata={"cli_version": "1.0.0"},
        )
        sid = upsert_session(conn, sess)
        sid2 = upsert_session(conn, sess)
        assert sid == sid2

        usage = TokenUsageRecord(
            provider_id="codex",
            session_id=sid,
            external_event_id="e-1",
            timestamp="2026-01-01T00:10:00+00:00",
            model_name="gpt-5",
            source="local_log",
            input_tokens=1,
            output_tokens=2,
            cached_tokens=3,
            reasoning_tokens=4,
            thoughts_tokens=5,
            tool_tokens=6,
            total_tokens=21,
            raw_data={"a": 1},
        )
        insert_token_usage(conn, usage)
        insert_token_usage(conn, usage)
        count = conn.execute("SELECT COUNT(*) FROM token_usage_history").fetchone()[0]
        assert count == 1
    finally:
        conn.close()


def test_insert_quota_and_indexes_exist(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    try:
        apply_migrations(conn)
        record = QuotaRecord(
            provider_id="gemini",
            quota_name="weekly",
            source="active_probe",
            timestamp="2026-01-01T00:00:00+00:00",
            used_percent=10.0,
            remaining_percent=90.0,
            window_minutes=10080,
            resets_at="2026-01-08T00:00:00+00:00",
            raw_data={"bucket": "x"},
        )
        insert_quota(conn, record)
        row = conn.execute("SELECT quota_name, source FROM quota_history").fetchone()
        assert row[0] == "weekly"
        assert row[1] == "active_probe"

        indexes = conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
        names = {r[0] for r in indexes}
        assert "idx_quota_history_provider_id" in names
        assert "idx_quota_history_timestamp" in names
        assert "idx_quota_history_quota_name" in names
        assert "idx_quota_history_resets_at" in names
    finally:
        conn.close()


def test_write_transaction_commit_and_rollback(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    try:
        apply_migrations(conn)
        insert_sql = "UPDATE providers SET updated_at = ? WHERE id = ?"
        with write_transaction(conn):
            conn.execute(insert_sql, ("2026-01-01T00:00:00+00:00", "gemini"))

        with pytest.raises(sqlite3.IntegrityError):
            with write_transaction(conn):
                dup_insert_sql = (
                    "INSERT INTO providers(id, enabled, config, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?)"
                )
                conn.execute(
                    dup_insert_sql,
                    ("gemini", 1, "{}", "x", "x"),
                )
    finally:
        conn.close()


def test_provider_validation_errors(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    try:
        apply_migrations(conn)
        sess = SessionRecord(
            provider_id="bad",
            external_session_id="x",
            model_name="unknown",
            project_path=None,
            project_name=None,
            created_at="2026-01-01T00:00:00+00:00",
            last_seen_at="2026-01-01T00:00:00+00:00",
            metadata={"cli_version": "x"},
        )
        with pytest.raises(ValueError):
            upsert_session(conn, sess)
    finally:
        conn.close()


def test_list_provider_health_sanitized_shape(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    try:
        apply_migrations(conn)
        rows = list_provider_health(conn)
        assert len(rows) == 4
        first = rows[0]
        assert set(first.keys()) == {"id", "enabled", "config", "updated_at"}
        assert "home_path" in first["config"]
        assert "safe_options" in first["config"]
    finally:
        conn.close()


def test_provider_row_helpers(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    try:
        apply_migrations(conn)
        assert get_provider_row(conn, "gemini") is not None
        assert get_provider_row(conn, "codex") is not None
        rows = list_provider_rows(conn)
        assert len(rows) == 4
        assert get_provider_row(conn, "gemini") is not None
        row = get_provider_row(conn, "gemini")
        assert row is not None
        cfg = dict(row["config"])
        cfg["home_path"] = "/tmp/custom"
        update_provider_row(conn, "gemini", enabled=False, config=cfg)
        conn.commit()
        row2 = get_provider_row(conn, "gemini")
        assert row2 is not None
        assert row2["enabled"] is False
        assert row2["config"]["home_path"] == "/tmp/custom"
        conn.execute("DELETE FROM providers WHERE id = 'gemini'")
        conn.commit()
        assert get_provider_row(conn, "gemini") is None
    finally:
        conn.close()
