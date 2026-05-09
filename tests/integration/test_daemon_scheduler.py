"""Integration tests for daemon scan/probe scheduler behavior."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from quota_tracker.api import create_app
from quota_tracker.daemon import DaemonService
from quota_tracker.db import (
    apply_migrations,
    connect_db,
    get_provider_row,
    update_provider_row,
)


def _write_gemini_fixture(home: Path, *, input_tokens: int) -> None:
    """Create one realistic Gemini chat file fixture."""

    chats = home / "tmp" / "run" / "chats"
    chats.mkdir(parents=True, exist_ok=True)
    (chats / "session-a.jsonl").write_text(
        json.dumps(
            {
                "id": "ev-1",
                "timestamp": "2026-01-01T00:00:00+00:00",
                "model": "gemini-2.5-pro",
                "tokens": {"input": input_tokens, "output": 2, "total": input_tokens + 2},
                "project_hash": "abc123",
                "cli_version": "0.40.1",
            }
        )
        + "\n"
    )


def test_daemon_full_then_incremental_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "quota.sqlite3"
    gemini_home = tmp_path / "gemini"
    _write_gemini_fixture(gemini_home, input_tokens=3)

    service = DaemonService(str(db_path))
    service.migrate_and_prepare()

    conn = connect_db(str(db_path))
    try:
        apply_migrations(conn)
        row = get_provider_row(conn, "gemini")
        assert row is not None
        cfg = dict(row["config"])
        cfg["home_path"] = str(gemini_home)
        cfg["passive_sync_enabled"] = True
        update_provider_row(conn, "gemini", enabled=True, config=cfg)
        conn.commit()
    finally:
        conn.close()

    first = service.run_scan(provider="gemini", full=True)
    second = service.run_scan(provider="gemini", full=False)

    assert first.sessions_upserted == 1
    assert first.token_rows_inserted == 1
    assert first.failed_providers == []
    assert second.sessions_upserted == 0
    assert second.token_rows_inserted == 0

    conn = connect_db(str(db_path))
    try:
        assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM token_usage_history").fetchone()[0] == 1
    finally:
        conn.close()


def test_provider_disable_and_reenable_resume(tmp_path: Path) -> None:
    db_path = tmp_path / "quota.sqlite3"
    gemini_home = tmp_path / "gemini"
    _write_gemini_fixture(gemini_home, input_tokens=5)
    service = DaemonService(str(db_path))
    service.migrate_and_prepare()

    conn = connect_db(str(db_path))
    try:
        row = get_provider_row(conn, "gemini")
        assert row is not None
        cfg = dict(row["config"])
        cfg["home_path"] = str(gemini_home)
        update_provider_row(conn, "gemini", enabled=True, config=cfg)
        conn.commit()
    finally:
        conn.close()

    service.run_scan(provider="gemini", full=True)
    service.set_provider_enabled("gemini", False)
    disabled = service.run_scan(provider="gemini", full=False)
    assert disabled.sessions_upserted == 0

    _write_gemini_fixture(gemini_home, input_tokens=7)
    service.set_provider_enabled("gemini", True)
    resumed = service.run_scan(provider="gemini", full=False)
    assert resumed.sessions_upserted == 1
    assert resumed.token_rows_inserted == 1


def test_manual_api_scan_probe_and_rescan(tmp_path: Path) -> None:
    db_path = tmp_path / "quota.sqlite3"
    gemini_home = tmp_path / "gemini"
    _write_gemini_fixture(gemini_home, input_tokens=4)
    (gemini_home / "oauth_creds.json").write_text("{}")

    service = DaemonService(str(db_path))
    service.migrate_and_prepare()

    conn = connect_db(str(db_path))
    try:
        row = get_provider_row(conn, "gemini")
        assert row is not None
        cfg = dict(row["config"])
        cfg["home_path"] = str(gemini_home)
        cfg["active_probe_enabled"] = True
        update_provider_row(conn, "gemini", enabled=True, config=cfg)
        conn.commit()
    finally:
        conn.close()

    client = TestClient(create_app(service=service, db_path=db_path))
    scan = client.post("/api/providers/gemini/scan", json={"full_rescan": False})
    probe = client.post("/api/providers/gemini/probe")
    rescan_fail = client.post("/api/providers/gemini/rescan", json={"full_rescan": False})
    rescan_ok = client.post("/api/providers/gemini/rescan", json={"full_rescan": True})

    assert scan.status_code == 200
    assert probe.status_code == 200
    assert rescan_fail.status_code == 200
    assert rescan_fail.json()["ok"] is False
    assert rescan_ok.status_code == 200
    assert rescan_ok.json()["ok"] is True
