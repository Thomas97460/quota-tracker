"""Gemini provider tests."""

import json
from pathlib import Path
from unittest.mock import patch

from quota_tracker.providers.gemini import GeminiProvider


def test_gemini_passive_and_incremental(tmp_path: Path) -> None:
    chats = tmp_path / "tmp" / "a" / "chats"
    chats.mkdir(parents=True)
    f = chats / "s1.jsonl"
    # JSONL with a gemini-type message that has tokens
    f.write_text(
        json.dumps(
            {
                "sessionId": "sess-1",
                "startTime": "2026-01-01T00:00:00+00:00",
            }
        )
        + "\n"
        + json.dumps(
            {
                "type": "gemini",
                "id": "ev-1",
                "timestamp": "2026-01-01T00:00:01+00:00",
                "model": "gemini-2.5-pro",
                "tokens": {"input": 1, "output": 2, "total": 3},
            }
        )
        + "\n"
    )
    p = GeminiProvider(str(tmp_path))
    full = p.passive_scan_full()
    assert len(full.sessions) == 1
    assert full.sessions[0].model_name == "gemini-2.5-pro"
    assert len(full.token_usage) == 1
    assert full.token_usage[0]["input_tokens"] == 1
    assert full.parse_failures == 0
    inc = p.passive_scan_incremental(full.high_water_marks)
    assert len(inc.sessions) == 0


def test_gemini_json_chat_file(tmp_path: Path) -> None:
    chats = tmp_path / "tmp" / "x" / "chats"
    chats.mkdir(parents=True)
    (chats / "chat.json").write_text(
        json.dumps(
            {
                "sessionId": "sess-json",
                "projectHash": "abc",
                "startTime": "2026-01-01T00:00:00+00:00",
                "messages": [
                    {
                        "type": "gemini",
                        "id": "m1",
                        "timestamp": "2026-01-01T00:00:01+00:00",
                        "model": "gemini-2.0-flash",
                        "tokens": {"input_tokens": 5, "output_tokens": 10, "total_tokens": 15},
                    }
                ],
            }
        )
    )
    p = GeminiProvider(str(tmp_path))
    result = p.passive_scan_full()
    assert len(result.sessions) == 1
    assert result.sessions[0].model_name == "gemini-2.0-flash"
    assert len(result.token_usage) == 1
    assert result.token_usage[0]["input_tokens"] == 5
    assert result.token_usage[0]["total_tokens"] == 15


def test_gemini_json_parse_failures(tmp_path: Path) -> None:
    chats = tmp_path / "tmp" / "x" / "chats"
    chats.mkdir(parents=True)
    (chats / "bad.jsonl").write_text("\n{bad}\n")
    (chats / "broken.json").write_text("{bad")
    p = GeminiProvider(str(tmp_path))
    result = p.passive_scan_full()
    assert result.parse_failures >= 2


def test_gemini_active_probe_paths(tmp_path: Path) -> None:
    p = GeminiProvider(str(tmp_path))
    assert p.active_probe() == []  # no oauth_creds.json

    (tmp_path / "oauth_creds.json").write_text("{}")
    assert p.active_probe() == []  # creds exist but no token or refresh_token


def test_gemini_no_tmp_dir(tmp_path: Path) -> None:
    p = GeminiProvider(str(tmp_path))
    result = p.passive_scan_full()
    assert result.sessions == []


def test_gemini_jsonl_set_record_and_dedup(tmp_path: Path) -> None:
    chats = tmp_path / "tmp" / "b" / "chats"
    chats.mkdir(parents=True)
    # Two identical messages without id should be deduped
    msg = {
        "type": "gemini",
        "timestamp": "2026-01-01T00:00:01+00:00",
        "model": "gemini-2.5-pro",
        "tokens": {"input": 5, "output": 3, "total": 8},
    }
    f = chats / "s2.jsonl"
    f.write_text(
        json.dumps({"sessionId": "s2", "startTime": "2026-01-01T00:00:00+00:00"})
        + "\n"
        + json.dumps({"$set": {"lastUpdated": "2026-01-01T01:00:00+00:00"}})
        + "\n"
        + json.dumps(msg)
        + "\n"
        + json.dumps(msg)
        + "\n"  # duplicate — should be deduped
    )
    p = GeminiProvider(str(tmp_path))
    result = p.passive_scan_full()
    assert len(result.sessions) == 1
    assert len(result.token_usage) == 1  # deduped


def test_gemini_subdirectory_chats(tmp_path: Path) -> None:
    sub = tmp_path / "tmp" / "x" / "chats" / "subdir"
    sub.mkdir(parents=True)
    (sub / "chat.json").write_text(
        json.dumps(
            {
                "sessionId": "sub-sess",
                "messages": [
                    {
                        "type": "gemini",
                        "id": "m1",
                        "timestamp": "2026-01-01T00:00:01+00:00",
                        "model": "gemini-2.0-flash",
                        "tokens": {"total_tokens": 10, "input_tokens": 5, "output_tokens": 5},
                    }
                ],
            }
        )
    )
    p = GeminiProvider(str(tmp_path))
    result = p.passive_scan_full()
    assert len(result.sessions) == 1
    assert len(result.token_usage) == 1


def test_gemini_json_non_dict_shape(tmp_path: Path) -> None:
    chats = tmp_path / "tmp" / "x" / "chats"
    chats.mkdir(parents=True)
    (chats / "list.json").write_text(json.dumps([1, 2, 3]))
    p = GeminiProvider(str(tmp_path))
    result = p.passive_scan_full()
    assert result.parse_failures >= 1


def test_gemini_edge_cases_in_scan(tmp_path: Path) -> None:
    chats = tmp_path / "tmp" / "x" / "chats"
    chats.mkdir(parents=True)
    # JSONL with non-dict record, non-gemini message, gemini with zero tokens
    f = chats / "edge.jsonl"
    f.write_text(
        json.dumps({"sessionId": "edge", "startTime": "2026-01-01T00:00:00+00:00", "lastUpdated": "2026-01-01T01:00:00+00:00"})
        + "\n"
        + "42\n"  # non-dict JSONL record
        + json.dumps({"type": "user", "timestamp": "2026-01-01T00:00:01+00:00", "content": "hi"})
        + "\n"  # non-gemini type
        + json.dumps({"type": "gemini", "timestamp": "2026-01-01T00:00:02+00:00", "model": "gemini-2.5-pro", "tokens": {"total": 0}})
        + "\n"  # gemini with total=0 — skip
    )
    # JSON with messages that is not a list
    (chats / "no-messages.json").write_text(
        json.dumps({"sessionId": "nm", "messages": "not-a-list"})
    )
    p = GeminiProvider(str(tmp_path))
    result = p.passive_scan_full()
    assert len(result.sessions) == 2
    assert len(result.token_usage) == 0


def test_gemini_non_dict_message_in_list(tmp_path: Path) -> None:
    chats = tmp_path / "tmp" / "x" / "chats"
    chats.mkdir(parents=True)
    (chats / "nondicts.json").write_text(
        json.dumps({"sessionId": "nd", "messages": ["string-not-dict", 42, None]})
    )
    p = GeminiProvider(str(tmp_path))
    result = p.passive_scan_full()
    assert len(result.sessions) == 1
    assert len(result.token_usage) == 0


def test_gemini_tok_int_invalid_value(tmp_path: Path) -> None:
    chats = tmp_path / "tmp" / "x" / "chats"
    chats.mkdir(parents=True)
    (chats / "bad-tokens.json").write_text(
        json.dumps(
            {
                "sessionId": "bad",
                "messages": [
                    {
                        "type": "gemini",
                        "id": "m1",
                        "timestamp": "2026-01-01T00:00:01+00:00",
                        "tokens": {"total_tokens": "not-a-number", "input_tokens": None},
                    }
                ],
            }
        )
    )
    p = GeminiProvider(str(tmp_path))
    result = p.passive_scan_full()
    assert len(result.token_usage) == 0


def test_gemini_active_probe_invalid_creds(tmp_path: Path) -> None:
    p = GeminiProvider(str(tmp_path))
    # Write invalid JSON to oauth_creds.json
    (tmp_path / "oauth_creds.json").write_text("{bad json")
    assert p.active_probe() == []

    # Write non-dict JSON
    (tmp_path / "oauth_creds.json").write_text(json.dumps([1, 2, 3]))
    assert p.active_probe() == []


def test_gemini_active_probe_no_project(tmp_path: Path) -> None:
    """Returns empty list when loadCodeAssist returns no project."""
    creds = {"access_token": "tok", "expiry_date": 9999999999000}
    (tmp_path / "oauth_creds.json").write_text(json.dumps(creds))
    p = GeminiProvider(str(tmp_path))
    with (
        patch("quota_tracker.providers.gemini._get_access_token", return_value="tok"),
        patch("quota_tracker.providers.gemini.post_json", return_value={}),
    ):
        assert p.active_probe() == []


def test_gemini_active_probe_exception(tmp_path: Path) -> None:
    """Network exception returns empty list."""
    creds = {"access_token": "tok", "expiry_date": 9999999999000}
    (tmp_path / "oauth_creds.json").write_text(json.dumps(creds))
    p = GeminiProvider(str(tmp_path))
    with (
        patch("quota_tracker.providers.gemini._get_access_token", return_value="tok"),
        patch("quota_tracker.providers.gemini.post_json", side_effect=RuntimeError("net")),
    ):
        assert p.active_probe() == []


def test_gemini_active_probe_granular(tmp_path: Path) -> None:
    """Gemini active_probe emits one row per (model_id, token_type) bucket."""
    creds = {"access_token": "tok", "expiry_date": 9999999999000}
    (tmp_path / "oauth_creds.json").write_text(json.dumps(creds))
    p = GeminiProvider(str(tmp_path))
    buckets = [
        {"model_id": "gemini-2.5-pro", "token_type": "input", "remaining_percent": 70.0, "used_percent": 30.0, "reset_time": None},
        {"model_id": "gemini-2.5-pro", "token_type": "output", "remaining_percent": 40.0, "used_percent": 60.0, "reset_time": None},
        {"model_id": "gemini-2.0-flash", "token_type": "input", "remaining_percent": 80.0, "used_percent": 20.0, "reset_time": None},
        {"model_id": "gemini-2.0-flash-lite", "token_type": "input", "remaining_percent": 50.0, "used_percent": 50.0, "reset_time": None},
    ]
    with (
        patch("quota_tracker.providers.gemini._get_access_token", return_value="tok"),
        patch("quota_tracker.providers.gemini.post_json", return_value={"cloudaicompanionProject": "proj"}),
        patch("quota_tracker.providers.gemini._retrieve_quota_buckets", return_value=buckets),
    ):
        records = p.active_probe()
    # One record per bucket
    assert len(records) == 4
    names = {r.quota_name for r in records}
    assert "gemini-2.5-pro/input" in names
    assert "gemini-2.5-pro/output" in names
    assert "gemini-2.0-flash/input" in names
    assert "gemini-2.0-flash-lite/input" in names
    for r in records:
        assert r.source == "active_probe"
