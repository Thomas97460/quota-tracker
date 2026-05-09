"""Snapshot tests for stable API JSON response shapes."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from quota_tracker.api import create_app
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


def _seed(db_path: Path) -> None:
    """Seed one deterministic set of rows for API shape assertions."""

    conn = connect_db(str(db_path))
    try:
        apply_migrations(conn)
        with write_transaction(conn):
            sid = upsert_session(
                conn,
                SessionRecord(
                    provider_id="codex",
                    external_session_id="s-1",
                    model_name="gpt-5",
                    project_path="/tmp/p",
                    project_name="p",
                    created_at="2026-01-01T00:00:00+00:00",
                    last_seen_at="2026-01-01T00:01:00+00:00",
                    metadata={"cli_version": "1.0.0"},
                ),
            )
            insert_token_usage(
                conn,
                TokenUsageRecord(
                    provider_id="codex",
                    session_id=sid,
                    external_event_id="e-1",
                    timestamp="2026-01-01T00:01:00+00:00",
                    model_name="gpt-5",
                    source="local_log",
                    input_tokens=1,
                    output_tokens=2,
                    cached_tokens=3,
                    reasoning_tokens=4,
                    thoughts_tokens=5,
                    tool_tokens=6,
                    total_tokens=21,
                    raw_data={"x": 1},
                ),
            )
            insert_quota(
                conn,
                QuotaRecord(
                    provider_id="codex",
                    quota_name="primary",
                    source="local_log",
                    timestamp="2026-01-01T00:01:00+00:00",
                    used_percent=25.0,
                    remaining_percent=75.0,
                    window_minutes=60,
                    resets_at="2026-01-01T01:00:00+00:00",
                    raw_data={"a": 1},
                ),
            )
    finally:
        conn.close()


def test_api_response_shapes_snapshot(tmp_path: Path) -> None:
    db_path = tmp_path / "api.sqlite3"
    _seed(db_path)
    app = create_app(db_path=db_path)
    client = TestClient(app)
    snapshot_path = (
        Path(__file__).resolve().parents[1] / "snapshots" / "api" / "expected_shapes.json"
    )
    expected = json.loads(snapshot_path.read_text())

    health = client.get("/api/health").json()
    providers = client.get("/api/providers").json()
    quotas = client.get("/api/quotas").json()
    sessions = client.get("/api/sessions").json()
    usage = client.get("/api/token-usage", params={"group_by": "provider"}).json()
    config = client.get("/api/config").json()

    assert sorted(health.keys()) == expected["health_keys"]
    assert sorted(providers["providers"][0].keys()) == expected["provider_item_keys"]
    assert sorted(quotas["items"][0].keys()) == expected["quota_item_keys"]
    assert sorted(sessions["items"][0].keys()) == expected["session_item_keys"]
    assert sorted(usage["items"][0].keys()) == expected["token_usage_item_keys"]
    assert sorted(config["config"].keys()) == expected["config_top_keys"]
