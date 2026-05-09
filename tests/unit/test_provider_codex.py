"""Codex provider tests."""

import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

from quota_tracker.providers.codex import CodexProvider, _epoch_to_iso


def test_codex_passive_and_rate_limits(tmp_path: Path) -> None:
    d = tmp_path / "sessions" / "p"
    d.mkdir(parents=True)
    f = d / "s1.jsonl"
    f.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "session_meta",
                        "timestamp": "2026-01-01T00:00:00+00:00",
                        "cli": {"version": "1.0"},
                    }
                ),
                json.dumps(
                    {
                        "type": "turn_context",
                        "timestamp": "2026-01-01T00:00:01+00:00",
                        "payload": {"model": "gpt-5"},
                    }
                ),
                json.dumps(
                    {
                        "type": "token_count",
                        "timestamp": "2026-01-01T00:00:02+00:00",
                        "usage": {"input_tokens": 2},
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-01-01T00:00:03+00:00",
                        "rate_limits": {
                            "primary": {"remaining_percent": 80},
                            "secondary": {"used_percent": 10},
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "event_msg",
                        "timestamp": "2026-01-01T00:00:04+00:00",
                        "payload": {
                            "type": "token_count",
                            "info": {
                                "total_token_usage": {
                                    "input_tokens": 11,
                                    "cached_input_tokens": 4,
                                    "output_tokens": 5,
                                    "reasoning_output_tokens": 2,
                                    "total_tokens": 18,
                                },
                                "last_token_usage": {
                                    "input_tokens": 3,
                                    "cached_input_tokens": 1,
                                    "output_tokens": 2,
                                    "reasoning_output_tokens": 1,
                                    "total_tokens": 5,
                                },
                            },
                            "rate_limits": {
                                "limit_name": "GPT-5.3-Codex-Spark",
                                "primary": {"used_percent": 20},
                                "secondary": {"remaining_percent": 70},
                            },
                        },
                    }
                ),
            ]
        )
    )
    p = CodexProvider(str(tmp_path))
    r = p.passive_scan_full()
    assert len(r.sessions) == 1
    assert len(r.token_usage) == 2
    assert r.token_usage[0]["input_tokens"] == 2
    assert r.token_usage[1]["model_name"] == "gpt-5"
    assert r.token_usage[1]["input_tokens"] == 3
    assert r.token_usage[1]["cached_tokens"] == 1
    assert r.token_usage[1]["output_tokens"] == 2
    assert r.token_usage[1]["reasoning_tokens"] == 1
    assert r.token_usage[1]["total_tokens"] == 5
    assert len(r.quotas) == 4


def test_codex_parse_failures_and_incremental_skip(tmp_path: Path) -> None:
    d = tmp_path / "sessions" / "p"
    d.mkdir(parents=True)
    f = d / "s1.jsonl"
    f.write_text("\n{bad json}\n")
    p = CodexProvider(str(tmp_path), include_archived=False)
    first = p.passive_scan_full()
    assert first.parse_failures == 1
    second = p.passive_scan_incremental(first.high_water_marks)
    assert len(second.sessions) == 0


def test_codex_archived_and_sqlite_readonly(tmp_path: Path) -> None:
    ad = tmp_path / "archived_sessions"
    ad.mkdir(parents=True)
    (ad / "a.jsonl").write_text(json.dumps({"timestamp": "2026-01-01T00:00:00+00:00"}))

    for name in ("state_5.sqlite", "logs_2.sqlite"):
        sqlite3.connect(tmp_path / name).close()

    p = CodexProvider(str(tmp_path), include_archived=True)
    r = p.passive_scan_full()
    assert len(r.sessions) == 1


def test_codex_active_probe_no_auth(tmp_path: Path) -> None:
    """Returns empty list when auth.json is missing."""
    p = CodexProvider(str(tmp_path))
    assert p.active_probe() == []


def test_codex_active_probe_missing_token(tmp_path: Path) -> None:
    """Returns empty list when access_token is absent."""
    (tmp_path / "auth.json").write_text(json.dumps({"tokens": {}}))
    p = CodexProvider(str(tmp_path))
    assert p.active_probe() == []


def test_codex_active_probe_wham(tmp_path: Path) -> None:
    """Parses primary/secondary windows from WHAM response."""
    auth = {
        "tokens": {
            "access_token": "tok-abc",
        }
    }
    (tmp_path / "auth.json").write_text(json.dumps(auth))
    p = CodexProvider(str(tmp_path))
    wham_response = {
        "rate_limit": {
            "primary_window": {
                "used_percent": 1,
                "limit_window_seconds": 18000,
                "reset_after_seconds": 18000,
                "reset_at": 1778343402,
            },
            "secondary_window": {
                "used_percent": 71,
                "limit_window_seconds": 604800,
                "reset_after_seconds": 285383,
                "reset_at": 1778610784,
            },
        }
    }
    with patch("quota_tracker.providers.codex.get_json", return_value=wham_response) as mock_get:
        records = p.active_probe()
    # Verify bearer token is passed in Authorization header
    call_headers = mock_get.call_args.kwargs["headers"]
    assert call_headers["Authorization"] == "Bearer tok-abc"
    assert len(records) == 2
    names = {r.quota_name for r in records}
    assert names == {"primary", "secondary"}
    primary = next(r for r in records if r.quota_name == "primary")
    assert primary.used_percent == 1.0
    assert primary.remaining_percent == 99.0
    assert primary.window_minutes == 300  # 18000 // 60
    assert primary.resets_at is not None
    assert primary.source == "active_probe"
    secondary = next(r for r in records if r.quota_name == "secondary")
    assert secondary.used_percent == 71.0


def test_codex_active_probe_missing_window(tmp_path: Path) -> None:
    """Missing secondary_window is skipped without crashing."""
    auth = {"tokens": {"access_token": "tok"}}
    (tmp_path / "auth.json").write_text(json.dumps(auth))
    p = CodexProvider(str(tmp_path))
    wham_response = {
        "rate_limit": {
            "primary_window": {
                "used_percent": 5,
                "limit_window_seconds": 18000,
                "reset_at": 1778343402,
            }
            # secondary_window absent
        }
    }
    with patch("quota_tracker.providers.codex.get_json", return_value=wham_response):
        records = p.active_probe()
    assert len(records) == 1
    assert records[0].quota_name == "primary"


def test_codex_active_probe_network_error(tmp_path: Path) -> None:
    """Network failure returns empty list."""
    auth = {"tokens": {"access_token": "tok"}}
    (tmp_path / "auth.json").write_text(json.dumps(auth))
    p = CodexProvider(str(tmp_path))
    with patch("quota_tracker.providers.codex.get_json", side_effect=RuntimeError("timeout")):
        assert p.active_probe() == []


def test_codex_active_probe_invalid_auth_json(tmp_path: Path) -> None:
    """Malformed auth.json returns empty list."""
    (tmp_path / "auth.json").write_text("{bad json")
    p = CodexProvider(str(tmp_path))
    assert p.active_probe() == []


def test_codex_active_probe_no_rate_limit_key(tmp_path: Path) -> None:
    """Response without rate_limit key returns empty list."""
    auth = {"tokens": {"access_token": "tok"}}
    (tmp_path / "auth.json").write_text(json.dumps(auth))
    p = CodexProvider(str(tmp_path))
    with patch("quota_tracker.providers.codex.get_json", return_value={"other": "data"}):
        assert p.active_probe() == []


def test_codex_epoch_to_iso() -> None:
    result = _epoch_to_iso(0)
    assert result is not None
    assert "1970" in result
    assert _epoch_to_iso(None) is None
    assert _epoch_to_iso("not-a-number") is None


def test_codex_session_meta_cwd(tmp_path: Path) -> None:
    d = tmp_path / "sessions" / "p"
    d.mkdir(parents=True)
    (d / "s1.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "session_meta",
                        "timestamp": "2026-01-01T00:00:00+00:00",
                        "payload": {"cwd": "/home/user/myproject"},
                    }
                ),
            ]
        )
    )
    p = CodexProvider(str(tmp_path))
    r = p.passive_scan_full()
    assert len(r.sessions) == 1
    assert r.sessions[0].project_path == "/home/user/myproject"
    assert r.sessions[0].project_name == "myproject"


def test_codex_secondary_none_skipped(tmp_path: Path) -> None:
    """secondary=None in rate_limits should be skipped gracefully (Fix #3)."""
    d = tmp_path / "sessions" / "p"
    d.mkdir(parents=True)
    (d / "s1.jsonl").write_text(
        json.dumps(
            {
                "timestamp": "2026-01-01T00:00:00+00:00",
                "rate_limits": {"primary": {"used_percent": 10}, "secondary": None},
            }
        )
    )
    p = CodexProvider(str(tmp_path))
    r = p.passive_scan_full()
    assert len(r.quotas) == 1
    assert r.quotas[0].quota_name == "primary"


def test_codex_model_from_payload(tmp_path: Path) -> None:
    """Model in turn_context must be read from payload.model (Fix #2)."""
    d = tmp_path / "sessions" / "p"
    d.mkdir(parents=True)
    (d / "s1.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "turn_context",
                        "timestamp": "2026-01-01T00:00:00+00:00",
                        "payload": {"model": "o3"},
                    }
                ),
                json.dumps(
                    {
                        "type": "token_count",
                        "timestamp": "2026-01-01T00:00:01+00:00",
                        "usage": {"input_tokens": 1},
                    }
                ),
            ]
        )
    )
    p = CodexProvider(str(tmp_path))
    r = p.passive_scan_full()
    assert len(r.token_usage) == 1
    assert r.token_usage[0]["model_name"] == "o3"


def test_codex_resets_at_epoch_conversion(tmp_path: Path) -> None:
    d = tmp_path / "sessions" / "p"
    d.mkdir(parents=True)
    (d / "s1.jsonl").write_text(
        json.dumps(
            {
                "timestamp": "2026-01-01T00:00:00+00:00",
                "rate_limits": {"primary": {"used_percent": 10, "resets_at": 1751328000}},
            }
        )
    )
    p = CodexProvider(str(tmp_path))
    r = p.passive_scan_full()
    assert len(r.quotas) == 1
    resets_at = r.quotas[0].resets_at
    assert resets_at is not None
    assert "T" in resets_at  # ISO format with time component
