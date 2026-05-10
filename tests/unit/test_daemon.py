"""Unit tests for daemon orchestration helpers."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from quota_tracker.daemon import DaemonService
from quota_tracker.db import apply_migrations, connect_db, get_provider_row, update_provider_row
from quota_tracker.providers import PassiveSyncResult


def test_provider_selector_and_reset_marks(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite3"
    service = DaemonService(str(db_path))
    service.migrate_and_prepare()

    assert service._provider_ids("all") == ["gemini", "codex", "copilot", "claude"]
    with pytest.raises(ValueError):
        service._provider_ids("x")

    conn = connect_db(str(db_path))
    try:
        row = get_provider_row(conn, "gemini")
        assert row is not None
        cfg = dict(row["config"])
        cfg["high_water_marks"] = {"a": 1}
        update_provider_row(conn, "gemini", enabled=True, config=cfg)
        conn.commit()
    finally:
        conn.close()

    service.reset_high_water_marks("gemini")
    conn = connect_db(str(db_path))
    try:
        row2 = get_provider_row(conn, "gemini")
        assert row2 is not None
        assert row2["config"]["high_water_marks"] == {}
    finally:
        conn.close()


def test_tick_due_logic_and_scheduler_start_stop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "db.sqlite3"
    service = DaemonService(str(db_path), sync_interval_minutes=15)
    service.migrate_and_prepare()

    calls: list[str] = []
    monkeypatch.setattr(
        service, "run_scan", lambda provider="all", full=False: calls.append("scan")
    )
    monkeypatch.setattr(service, "run_probe", lambda provider="all": calls.append("probe"))
    service.tick()
    assert "scan" in calls
    assert "probe" in calls

    conn = connect_db(str(db_path))
    try:
        apply_migrations(conn)
        for provider in ("gemini", "codex", "copilot", "claude"):
            row = get_provider_row(conn, provider)
            assert row is not None
            cfg = dict(row["config"])
            safe = dict(cfg.get("safe_options", {}))
            safe["last_successful_sync_at"] = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
            safe["last_successful_probe_at"] = datetime.now(UTC).isoformat()
            cfg["safe_options"] = safe
            update_provider_row(conn, provider, enabled=True, config=cfg)
        conn.commit()
    finally:
        conn.close()

    calls.clear()
    service.tick()
    assert calls == []

    service.start_scheduler(sleep_seconds=0.01)
    service.stop_scheduler()


def test_provider_instance_variants(tmp_path: Path) -> None:
    service = DaemonService(str(tmp_path / "db.sqlite3"))
    gemini = service._provider_instance("gemini", {"home_path": str(tmp_path)})
    codex = service._provider_instance(
        "codex", {"home_path": str(tmp_path), "safe_options": {"include_archived": False}}
    )
    copilot = service._provider_instance("copilot", {"home_path": str(tmp_path)})
    assert gemini.metadata.id == "gemini"
    assert codex.metadata.id == "codex"
    assert copilot.metadata.id == "copilot"
    with pytest.raises(ValueError):
        service._provider_instance("other", {"home_path": str(tmp_path)})


def test_run_scan_quotas_and_probe_failure_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "db.sqlite3"
    service = DaemonService(str(db_path))
    service.migrate_and_prepare()

    class FakeProvider:
        metadata = None

        def passive_scan_full(self) -> PassiveSyncResult:
            return PassiveSyncResult(
                sessions=[],
                token_usage=[],
                quotas=[],
                high_water_marks={},
                parse_failures=0,
            )

        def passive_scan_incremental(
            self, high_water_marks: dict[str, object]
        ) -> PassiveSyncResult:
            return PassiveSyncResult(
                sessions=[
                    type(
                        "S",
                        (),
                        {
                            "provider_id": "gemini",
                            "external_session_id": "session-1",
                            "model_name": "unknown",
                            "project_path": None,
                            "project_name": None,
                            "created_at": "2026-01-01T00:00:00+00:00",
                            "last_seen_at": "2026-01-01T00:00:00+00:00",
                            "metadata": {},
                        },
                    )()
                ],
                token_usage=[
                    {
                        "provider_id": "gemini",
                        "external_session_id": "other",
                        "external_event_id": "e1",
                        "timestamp": "2026-01-01T00:00:00+00:00",
                        "model_name": "unknown",
                        "source": "local_log",
                        "input_tokens": 1,
                        "output_tokens": 0,
                        "cached_tokens": 0,
                        "reasoning_tokens": 0,
                        "thoughts_tokens": 0,
                        "tool_tokens": 0,
                        "total_tokens": 1,
                        "raw_metadata": {},
                    }
                ],
                quotas=[
                    type(
                        "Q",
                        (),
                        {
                            "provider_id": "gemini",
                            "quota_name": "default",
                            "source": "local_log",
                            "timestamp": "2026-01-01T00:00:00+00:00",
                            "used_percent": 10.0,
                            "remaining_percent": 90.0,
                            "window_minutes": 60,
                            "resets_at": None,
                            "raw_data": {},
                        },
                    )()
                ],
                high_water_marks={},
                parse_failures=0,
            )

        def active_probe(self) -> list[object]:
            raise RuntimeError("boom")

    monkeypatch.setattr(service, "_provider_instance", lambda provider_id, config: FakeProvider())
    summary = service.run_scan(provider="gemini", full=False)
    assert summary.sessions_upserted == 1
    assert summary.quota_rows_inserted == 1

    service.run_probe(provider="gemini")
    conn = connect_db(str(db_path))
    try:
        row2 = get_provider_row(conn, "gemini")
        assert row2 is not None
        assert "last_probe_error" in row2["config"]["safe_options"]
    finally:
        conn.close()


def test_run_scan_inserts_quota_and_run_probe_skip(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite3"
    service = DaemonService(str(db_path))
    service.migrate_and_prepare()
    codex_home = tmp_path / "empty-codex"
    codex_home.mkdir()
    conn = connect_db(str(db_path))
    try:
        row = get_provider_row(conn, "codex")
        assert row is not None
        cfg = dict(row["config"])
        cfg["home_path"] = str(codex_home)
        update_provider_row(conn, "codex", enabled=True, config=cfg)
        conn.commit()
    finally:
        conn.close()

    summary = service.run_scan(provider="codex", full=True)
    assert summary.quota_rows_inserted == 0
    probe = service.run_probe(provider="codex")
    assert probe.quota_rows_inserted == 0


def test_run_scan_and_probe_skip_disabled_provider(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite3"
    service = DaemonService(str(db_path))
    service.migrate_and_prepare()
    service.set_provider_enabled("codex", False)
    scan = service.run_scan(provider="codex", full=False)
    assert scan.sessions_upserted == 0
    probe = service.run_probe(provider="codex")
    assert probe.quota_rows_inserted == 0


def test_run_probe_inserts_quota_records(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite3"
    service = DaemonService(str(db_path))
    service.migrate_and_prepare()
    codex_home = tmp_path / "codex"
    codex_home.mkdir()
    auth = {"tokens": {"access_token": "tok-test"}}
    (codex_home / "auth.json").write_text(json.dumps(auth))
    conn = connect_db(str(db_path))
    try:
        row = get_provider_row(conn, "codex")
        assert row is not None
        cfg = dict(row["config"])
        cfg["home_path"] = str(codex_home)
        update_provider_row(conn, "codex", enabled=True, config=cfg)
        conn.commit()
    finally:
        conn.close()
    wham_response = {
        "rate_limit": {
            "primary_window": {
                "used_percent": 5,
                "limit_window_seconds": 18000,
                "reset_at": 1778343402,
            }
        }
    }
    with patch("quota_tracker.providers.codex.get_json", return_value=wham_response):
        probe = service.run_probe(provider="codex")
    assert probe.quota_rows_inserted == 1


def test_tick_disabled_provider_not_due(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "db.sqlite3"
    service = DaemonService(str(db_path), sync_interval_minutes=5)
    service.migrate_and_prepare()
    service.set_provider_enabled("gemini", False)
    service.set_provider_enabled("codex", False)
    service.set_provider_enabled("copilot", False)
    service.set_provider_enabled("claude", False)
    called: list[str] = []
    monkeypatch.setattr(
        service, "run_scan", lambda provider="all", full=False: called.append("scan")
    )
    monkeypatch.setattr(service, "run_probe", lambda provider="all": called.append("probe"))
    service.tick()
    assert called == []


def test_tick_due_thresholds_and_missing_provider_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "db.sqlite3"
    service = DaemonService(str(db_path), sync_interval_minutes=15)
    service.migrate_and_prepare()

    conn = connect_db(str(db_path))
    try:
        now = datetime.now(UTC)
        row = get_provider_row(conn, "gemini")
        assert row is not None
        cfg = dict(row["config"])
        cfg["safe_options"] = {
            "last_successful_sync_at": (now - timedelta(minutes=16)).isoformat(),
        }
        update_provider_row(conn, "gemini", enabled=True, config=cfg)
        conn.commit()
    finally:
        conn.close()

    calls: list[str] = []
    monkeypatch.setattr(
        service, "run_scan", lambda provider="all", full=False: calls.append("scan")
    )
    monkeypatch.setattr(service, "run_probe", lambda provider="all": calls.append("probe"))
    service.tick()
    assert calls == ["scan", "probe", "probe", "probe", "probe"]

    service.set_provider_enabled("copilot", True)
    service.reset_high_water_marks("copilot")


def test_start_scheduler_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = DaemonService(str(tmp_path / "db.sqlite3"))
    service.migrate_and_prepare()
    monkeypatch.setattr(service, "tick", lambda: None)
    service.start_scheduler(sleep_seconds=0.01)
    service.start_scheduler(sleep_seconds=0.01)
    service.stop_scheduler()


def test_tick_not_due_when_recent_sync(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "db.sqlite3"
    service = DaemonService(str(db_path), sync_interval_minutes=60)
    service.migrate_and_prepare()
    conn = connect_db(str(db_path))
    try:
        for provider in ("gemini", "codex", "copilot", "claude"):
            row = get_provider_row(conn, provider)
            assert row is not None
            cfg = dict(row["config"])
            cfg["safe_options"] = {
                "last_successful_sync_at": datetime.now(UTC).isoformat(),
                "last_successful_probe_at": datetime.now(UTC).isoformat(),
            }
            update_provider_row(conn, provider, enabled=True, config=cfg)
        conn.commit()
    finally:
        conn.close()
    called: list[str] = []
    monkeypatch.setattr(
        service, "run_scan", lambda provider="all", full=False: called.append("scan")
    )
    monkeypatch.setattr(service, "run_probe", lambda provider="all": called.append("probe"))
    service.tick()
    assert called == []


def test_missing_provider_row_noop_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = DaemonService(str(tmp_path / "db.sqlite3"))
    service.migrate_and_prepare()
    monkeypatch.setattr("quota_tracker.daemon.get_provider_row", lambda conn, provider_id: None)
    service.set_provider_enabled("gemini", True)
    service.reset_high_water_marks("gemini")
