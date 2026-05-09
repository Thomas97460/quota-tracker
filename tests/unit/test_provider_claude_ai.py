"""Claude.ai provider tests."""

import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

from quota_tracker.providers.claude_ai import (
    ClaudeAiProvider,
    _fetch_org_id,
    _load_session_key,
    _load_session_key_from_file,
    _load_session_key_from_firefox,
    _parse_usage_response,
)

# Real API response observed 2026-05-09
_REAL_RESPONSE = {
    "five_hour": {"utilization": 22.0, "resets_at": "2026-05-09T19:10:00.814908+00:00"},
    "seven_day": {"utilization": 43.0, "resets_at": "2026-05-13T05:00:00.814930+00:00"},
    "seven_day_oauth_apps": None,
    "seven_day_opus": None,
    "seven_day_sonnet": None,
    "seven_day_cowork": None,
    "seven_day_omelette": {"utilization": 85.0, "resets_at": "2026-05-13T05:00:00.814944+00:00"},
    "tangelo": None,
    "iguana_necktie": None,
    "omelette_promotional": None,
    "extra_usage": {
        "is_enabled": False,
        "monthly_limit": None,
        "used_credits": None,
        "utilization": None,
        "currency": None,
    },
}


def _write_claude_project_file(tmp_path: Path) -> Path:
    project = tmp_path / "projects" / "-home-collet-Bureau-quota-tracker"
    project.mkdir(parents=True)
    transcript = project / "session-1.jsonl"
    transcript.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "user",
                        "uuid": "u1",
                        "timestamp": "2026-05-09T10:00:00.000Z",
                        "sessionId": "session-1",
                        "cwd": "/home/collet/Bureau/quota-tracker",
                        "version": "2.1.123",
                        "gitBranch": "main",
                        "message": {"role": "user", "content": "do not persist"},
                    }
                ),
                json.dumps(
                    {
                        "type": "assistant",
                        "uuid": "a1",
                        "timestamp": "2026-05-09T10:00:05.000Z",
                        "sessionId": "session-1",
                        "cwd": "/home/collet/Bureau/quota-tracker",
                        "version": "2.1.123",
                        "gitBranch": "main",
                        "message": {
                            "id": "msg_1",
                            "type": "message",
                            "model": "claude-sonnet-4-6",
                            "content": [{"type": "text", "text": "do not persist"}],
                            "usage": {
                                "input_tokens": 3,
                                "cache_creation_input_tokens": 7,
                                "cache_read_input_tokens": 11,
                                "output_tokens": 13,
                                "server_tool_use": {"web_search_requests": 2},
                                "service_tier": "standard",
                            },
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "assistant",
                        "uuid": "a2",
                        "timestamp": "2026-05-09T10:00:06.000Z",
                        "sessionId": "session-1",
                        "message": {
                            "id": "msg_1",
                            "type": "message",
                            "model": "claude-sonnet-4-6",
                            "usage": {
                                "input_tokens": 5,
                                "cache_creation_input_tokens": 7,
                                "cache_read_input_tokens": 11,
                                "output_tokens": 17,
                            },
                        },
                    }
                ),
            ]
        )
    )
    return transcript


def test_passive_scan_reads_claude_code_sessions_and_tokens(tmp_path: Path) -> None:
    _write_claude_project_file(tmp_path)
    provider = ClaudeAiProvider(home=str(tmp_path))
    result = provider.passive_scan_full()
    assert len(result.sessions) == 1
    assert result.sessions[0].external_session_id == "session-1"
    assert result.sessions[0].model_name == "claude-sonnet-4-6"
    assert result.sessions[0].project_name == "quota-tracker"
    assert result.sessions[0].metadata["cli_version"] == "2.1.123"
    assert len(result.token_usage) == 1
    usage = result.token_usage[0]
    assert usage["external_event_id"] == "msg_1"
    assert usage["input_tokens"] == 5
    assert usage["cached_tokens"] == 18
    assert usage["output_tokens"] == 17
    assert usage["total_tokens"] == 40
    assert "content" not in usage["raw_metadata"]
    assert result.quotas == []
    assert result.parse_failures == 0


def test_passive_scan_incremental_skips_unchanged_file(tmp_path: Path) -> None:
    _write_claude_project_file(tmp_path)
    provider = ClaudeAiProvider(home=str(tmp_path))
    first = provider.passive_scan_full()
    result = provider.passive_scan_incremental(first.high_water_marks)
    assert result.sessions == []
    assert result.token_usage == []


# ── _load_session_key_from_file ───────────────────────────────────────────────


def test_load_session_key_from_file_missing(tmp_path: Path) -> None:
    assert _load_session_key_from_file(tmp_path) is None


def test_load_session_key_from_file_invalid_json(tmp_path: Path) -> None:
    (tmp_path / "quota_tracker_creds.json").write_text("not json")
    assert _load_session_key_from_file(tmp_path) is None


def test_load_session_key_from_file_missing_key(tmp_path: Path) -> None:
    (tmp_path / "quota_tracker_creds.json").write_text(json.dumps({"organization_id": "x"}))
    assert _load_session_key_from_file(tmp_path) is None


def test_load_session_key_from_file_valid(tmp_path: Path) -> None:
    (tmp_path / "quota_tracker_creds.json").write_text(
        json.dumps({"session_key": "sk-ant-sid02-abc"})
    )
    assert _load_session_key_from_file(tmp_path) == "sk-ant-sid02-abc"


def test_load_session_key_from_file_old_format_with_org_id(tmp_path: Path) -> None:
    """Old format with organization_id still works (org_id ignored, session_key returned)."""
    (tmp_path / "quota_tracker_creds.json").write_text(
        json.dumps({"session_key": "sk-ant-sid02-abc", "organization_id": "org-123"})
    )
    assert _load_session_key_from_file(tmp_path) == "sk-ant-sid02-abc"


# ── _load_session_key_from_firefox ───────────────────────────────────────────


def _make_firefox_cookies_db(tmp_path: Path, session_key: str | None) -> Path:
    """Create a minimal Firefox cookies.sqlite with an optional claude.ai sessionKey."""
    profile = tmp_path / ".mozilla" / "firefox" / "test.default"
    profile.mkdir(parents=True)
    db_path = profile / "cookies.sqlite"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE moz_cookies ("
        "id INTEGER PRIMARY KEY, host TEXT, name TEXT, value TEXT, expiry INTEGER)"
    )
    if session_key is not None:
        conn.execute(
            "INSERT INTO moz_cookies (host, name, value, expiry) VALUES (?, ?, ?, ?)",
            (".claude.ai", "sessionKey", session_key, 9999999999),
        )
    conn.commit()
    conn.close()
    return db_path


def test_load_session_key_from_firefox_no_mozilla_dir(tmp_path: Path) -> None:
    with patch("quota_tracker.providers.claude_ai.Path.home", return_value=tmp_path):
        assert _load_session_key_from_firefox() is None


def test_load_session_key_from_firefox_no_cookie(tmp_path: Path) -> None:
    _make_firefox_cookies_db(tmp_path, session_key=None)
    with patch("quota_tracker.providers.claude_ai.Path.home", return_value=tmp_path):
        assert _load_session_key_from_firefox() is None


def test_load_session_key_from_firefox_found(tmp_path: Path) -> None:
    _make_firefox_cookies_db(tmp_path, session_key="sk-ant-sid02-firefox")
    with patch("quota_tracker.providers.claude_ai.Path.home", return_value=tmp_path):
        assert _load_session_key_from_firefox() == "sk-ant-sid02-firefox"


# ── _load_session_key (combined) ─────────────────────────────────────────────


def test_load_session_key_prefers_file_over_firefox(tmp_path: Path) -> None:
    (tmp_path / "quota_tracker_creds.json").write_text(json.dumps({"session_key": "sk-from-file"}))
    _make_firefox_cookies_db(tmp_path, session_key="sk-from-firefox")
    with patch("quota_tracker.providers.claude_ai.Path.home", return_value=tmp_path):
        assert _load_session_key(tmp_path) == "sk-from-file"


def test_load_session_key_falls_back_to_firefox(tmp_path: Path) -> None:
    _make_firefox_cookies_db(tmp_path, session_key="sk-ant-sid02-fox")
    with patch("quota_tracker.providers.claude_ai.Path.home", return_value=tmp_path):
        assert _load_session_key(tmp_path) == "sk-ant-sid02-fox"


def test_load_session_key_returns_none_when_nothing(tmp_path: Path) -> None:
    with patch("quota_tracker.providers.claude_ai.Path.home", return_value=tmp_path):
        assert _load_session_key(tmp_path) is None


# ── _fetch_org_id ─────────────────────────────────────────────────────────────


def test_fetch_org_id_success() -> None:
    # get_json wraps list responses as {"value": [...]}
    mock_response = {"value": [{"uuid": "org-uuid-123", "id": 42, "name": "My Org"}]}
    with patch("quota_tracker.providers.claude_ai.get_json", return_value=mock_response):
        assert _fetch_org_id("sk-ant-sid02-x") == "org-uuid-123"


def test_fetch_org_id_empty_value_list() -> None:
    with patch("quota_tracker.providers.claude_ai.get_json", return_value={"value": []}):
        assert _fetch_org_id("sk-ant-sid02-x") is None


def test_fetch_org_id_no_value_key() -> None:
    with patch("quota_tracker.providers.claude_ai.get_json", return_value={"error": "bad"}):
        assert _fetch_org_id("sk-ant-sid02-x") is None


def test_fetch_org_id_request_fails() -> None:
    with patch("quota_tracker.providers.claude_ai.get_json", side_effect=Exception("timeout")):
        assert _fetch_org_id("sk-ant-sid02-x") is None


# ── active_probe ──────────────────────────────────────────────────────────────


def test_active_probe_no_credentials(tmp_path: Path) -> None:
    with patch("quota_tracker.providers.claude_ai.Path.home", return_value=tmp_path):
        provider = ClaudeAiProvider(home=str(tmp_path))
        assert provider.active_probe() == []


def test_active_probe_org_fetch_fails(tmp_path: Path) -> None:
    (tmp_path / "quota_tracker_creds.json").write_text(
        json.dumps({"session_key": "sk-ant-sid02-x"})
    )
    with patch("quota_tracker.providers.claude_ai.get_json", side_effect=Exception("403")):
        provider = ClaudeAiProvider(home=str(tmp_path))
        assert provider.active_probe() == []


# ── _parse_usage_response ─────────────────────────────────────────────────────


def test_parse_usage_response_real_format() -> None:
    """Parse the real API response observed from claude.ai."""
    records = _parse_usage_response(_REAL_RESPONSE, "2026-05-09T12:00:00+00:00")
    by_name = {r.quota_name: r for r in records}

    # five_hour → "5h"
    assert "5h" in by_name
    fiveh = by_name["5h"]
    assert fiveh.used_percent == 22.0
    assert fiveh.remaining_percent == 78.0
    assert fiveh.window_minutes == 300
    assert fiveh.resets_at == "2026-05-09T19:10:00.814908+00:00"

    # seven_day → "weekly"
    assert "weekly" in by_name
    weekly = by_name["weekly"]
    assert weekly.used_percent == 43.0
    assert weekly.remaining_percent == 57.0
    assert weekly.window_minutes == 10080
    assert weekly.resets_at == "2026-05-13T05:00:00.814930+00:00"

    # seven_day_omelette kept under its own name
    assert "seven_day_omelette" in by_name
    omelette = by_name["seven_day_omelette"]
    assert omelette.used_percent == 85.0

    # null buckets are skipped
    assert "seven_day_opus" not in by_name
    assert "seven_day_sonnet" not in by_name

    # extra_usage has utilization=null → skipped
    assert "extra_usage" not in by_name


def test_parse_usage_response_null_utilization_skipped() -> None:
    data = {
        "five_hour": {"utilization": None, "resets_at": "2026-05-09T19:00:00+00:00"},
        "seven_day": {"utilization": 50.0, "resets_at": "2026-05-13T05:00:00+00:00"},
    }
    records = _parse_usage_response(data, "2026-05-09T12:00:00+00:00")
    assert len(records) == 1
    assert records[0].quota_name == "weekly"


def test_parse_usage_response_empty() -> None:
    assert _parse_usage_response({}, "2026-05-09T12:00:00+00:00") == []


def test_parse_usage_response_all_null() -> None:
    data = {"five_hour": None, "seven_day": None, "seven_day_opus": None}
    assert _parse_usage_response(data, "2026-05-09T12:00:00+00:00") == []


def test_parse_usage_response_zero_utilization() -> None:
    data = {"five_hour": {"utilization": 0.0, "resets_at": "2026-05-09T19:00:00+00:00"}}
    records = _parse_usage_response(data, "2026-05-09T12:00:00+00:00")
    assert records[0].used_percent == 0.0
    assert records[0].remaining_percent == 100.0


def test_parse_usage_response_provider_and_source() -> None:
    data = {"seven_day": {"utilization": 10.0, "resets_at": "2026-05-13T05:00:00+00:00"}}
    records = _parse_usage_response(data, "2026-05-09T12:00:00+00:00")
    assert records[0].provider_id == "claude"
    assert records[0].source == "active_probe"
