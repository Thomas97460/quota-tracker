"""Integration tests for migration and read/write flow."""

from pathlib import Path

from quota_tracker.db import (
    QuotaRecord,
    SessionRecord,
    TokenUsageRecord,
    apply_migrations,
    connect_db,
    insert_quota,
    insert_token_usage,
    upsert_session,
    write_transaction,
)


def test_full_flow(tmp_path: Path) -> None:
    conn = connect_db(str(tmp_path / "flow.sqlite3"))
    try:
        apply_migrations(conn)
        with write_transaction(conn):
            sid = upsert_session(
                conn,
                SessionRecord(
                    provider_id="copilot",
                    external_session_id="sess-42",
                    model_name="gpt-4.1",
                    project_path=None,
                    project_name="demo",
                    created_at="2026-02-01T00:00:00+00:00",
                    last_seen_at="2026-02-01T00:05:00+00:00",
                    metadata={"cli_version": "1.0.40", "parse_version": "v1"},
                ),
            )
            insert_token_usage(
                conn,
                TokenUsageRecord(
                    provider_id="copilot",
                    session_id=sid,
                    external_event_id="evt-1",
                    timestamp="2026-02-01T00:05:00+00:00",
                    model_name="gpt-4.1",
                    source="provider_db",
                    input_tokens=10,
                    output_tokens=20,
                    cached_tokens=0,
                    reasoning_tokens=0,
                    thoughts_tokens=0,
                    tool_tokens=0,
                    total_tokens=30,
                    raw_data={"origin": "fixture"},
                ),
            )
            insert_quota(
                conn,
                QuotaRecord(
                    provider_id="copilot",
                    quota_name="weekly",
                    source="active_probe",
                    timestamp="2026-02-01T00:05:00+00:00",
                    used_percent=33.3,
                    remaining_percent=66.7,
                    window_minutes=10080,
                    resets_at="2026-02-08T00:00:00+00:00",
                    raw_data={"header": "x-usage-ratelimit-weekly"},
                ),
            )

        assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM token_usage_history").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM quota_history").fetchone()[0] == 1
    finally:
        conn.close()
