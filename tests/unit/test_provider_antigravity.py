"""Tests for Antigravity CLI provider."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from quota_tracker.providers.antigravity import AntigravityProvider, _normalize_model_name


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("Gemini 3.6 Flash (High)", "gemini-3.6-flash"),
        ("Gemini 3.5 Flash-Lite", "gemini-3.5-flash-lite"),
        ("Claude Opus 5 (Thinking)", "claude-opus-5"),
    ],
)
def test_normalize_latest_model_labels(label: str, expected: str) -> None:
    assert _normalize_model_name(label) == expected


def test_antigravity_passive_scan_reads_history_logs_and_conversations(tmp_path: Path) -> None:
    home = tmp_path / ".gemini" / "antigravity-cli"
    (home / "cache").mkdir(parents=True)
    (home / "log").mkdir()
    (home / "conversations").mkdir()
    (home / "settings.json").write_text(
        json.dumps({"model": "Gemini 3.5 Flash (High)"}),
        encoding="utf-8",
    )
    (home / "history.jsonl").write_text(
        json.dumps(
            {
                "timestamp": 1780230618480,
                "workspace": str(tmp_path / "quota-tracker"),
                "conversationId": "11111111-1111-4111-8111-111111111111",
                "display": "redacted by parser",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (home / "cache" / "last_conversations.json").write_text(
        json.dumps({str(tmp_path / "other"): "22222222-2222-4222-8222-222222222222"}),
        encoding="utf-8",
    )
    (home / "log" / "cli-20260531_142919.log").write_text(
        "\n".join(
            [
                "I0531 14:29:19.793519 14328 common.go:156] project: using project "
                f'"{tmp_path / "quota-tracker"}" '
                "(id=project-id) at /tmp/project.json",
                "I0531 14:29:19.795396 14328 manager.go:249] "
                f"Initializing CLI store manager for workspace {tmp_path / 'quota-tracker'}",
                "I0531 14:29:57.231695 14328 model_config_manager.go:157] "
                'Propagating selected model override to backend: label="Gemini 3.5 Flash (High)"',
                "I0531 14:29:57.519151 14328 server.go:747] "
                "Created conversation 33333333-3333-4333-8333-333333333333",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (home / "conversations" / "44444444-4444-4444-8444-444444444444.pb").write_bytes(b"opaque")

    result = AntigravityProvider(str(home)).passive_scan_full()

    by_id = {s.external_session_id: s for s in result.sessions}
    assert sorted(by_id) == [
        "11111111-1111-4111-8111-111111111111",
        "22222222-2222-4222-8222-222222222222",
        "33333333-3333-4333-8333-333333333333",
        "44444444-4444-4444-8444-444444444444",
    ]
    logged = by_id["33333333-3333-4333-8333-333333333333"]
    assert logged.provider_id == "antigravity"
    assert logged.model_name == "gemini-3.5-flash"
    assert logged.project_path == str(tmp_path / "quota-tracker")
    assert logged.project_name == "quota-tracker"
    assert result.token_usage == []
    assert result.quotas == []
    assert result.parse_failures == 0
    assert result.high_water_marks


def test_antigravity_incremental_skips_unchanged_files(tmp_path: Path) -> None:
    home = tmp_path / ".gemini" / "antigravity-cli"
    home.mkdir(parents=True)
    (home / "history.jsonl").write_text(
        json.dumps(
            {
                "timestamp": 1780230618480,
                "workspace": str(tmp_path),
                "conversationId": "11111111-1111-4111-8111-111111111111",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    provider = AntigravityProvider(str(home))
    first = provider.passive_scan_full()
    second = provider.passive_scan_incremental(first.high_water_marks)

    assert len(first.sessions) == 1
    assert second.sessions == []
    assert second.high_water_marks == first.high_water_marks


def test_antigravity_active_probe_returns_empty(tmp_path: Path) -> None:
    gemini_home = tmp_path / ".gemini"
    home = gemini_home / "antigravity-cli"
    home.mkdir(parents=True)
    records = AntigravityProvider(str(home)).active_probe()
    assert records == []


def test_antigravity_passive_scan_db(tmp_path: Path) -> None:
    home = tmp_path / ".gemini" / "antigravity-cli"
    conv_dir = home / "conversations"
    conv_dir.mkdir(parents=True)

    db_path = conv_dir / "test-conv-id.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE gen_metadata (idx INTEGER PRIMARY KEY, data BLOB, size INTEGER);")

    # Let's construct raw protobuf bytes for a row
    def make_varint(fn: int, val: int) -> bytes:
        tag = (fn << 3) | 0
        out = bytearray()
        while True:
            b = tag & 0x7F
            tag >>= 7
            if tag:
                out.append(b | 0x80)
            else:
                out.append(b)
                break
        while True:
            b = val & 0x7F
            val >>= 7
            if val:
                out.append(b | 0x80)
            else:
                out.append(b)
                break
        return bytes(out)

    def make_length_delimited(fn: int, val: bytes) -> bytes:
        tag = (fn << 3) | 2
        out = bytearray()
        while True:
            b = tag & 0x7F
            tag >>= 7
            if tag:
                out.append(b | 0x80)
            else:
                out.append(b)
                break
        length = len(val)
        while True:
            b = length & 0x7F
            length >>= 7
            if length:
                out.append(b | 0x80)
            else:
                out.append(b)
                break
        out.extend(val)
        return bytes(out)

    # field 4 in root (timestamp)
    ts_seconds = make_varint(1, 1780937561)  # 2026-06-08 16:52:41 UTC
    ts_proto_bytes = make_length_delimited(4, ts_seconds)

    # field 1 in root (metadata)
    model_label_bytes = make_length_delimited(21, b"Claude Opus 4.6 (Thinking)")
    # field 4 in metadata (token usage)
    input_varint = make_varint(9, 100)
    output_varint = make_varint(10, 50)
    event_id_bytes = make_length_delimited(11, b"event-123")
    token_usage_bytes = make_length_delimited(4, input_varint + output_varint + event_id_bytes)

    metadata_bytes = make_length_delimited(1, model_label_bytes + token_usage_bytes)

    full_blob = ts_proto_bytes + metadata_bytes

    cursor.execute(
        "INSERT INTO gen_metadata (idx, data, size) VALUES (?, ?, ?);",
        (0, full_blob, len(full_blob)),
    )
    conn.commit()
    conn.close()

    result = AntigravityProvider(str(home)).passive_scan_full()

    assert len(result.sessions) == 1
    session = result.sessions[0]
    assert session.external_session_id == "test-conv-id"
    assert session.model_name == "claude-opus-4.6"
    assert session.created_at == "2026-06-08T16:52:41+00:00"

    assert len(result.token_usage) == 1
    usage = result.token_usage[0]
    assert usage["provider_id"] == "antigravity"
    assert usage["external_session_id"] == "test-conv-id"
    assert usage["external_event_id"] == "event-123"
    assert usage["model_name"] == "claude-opus-4.6"
    assert usage["input_tokens"] == 100
    assert usage["output_tokens"] == 50


def test_antigravity_active_probe_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / ".gemini" / "antigravity-cli"
    (home / "log").mkdir(parents=True)
    (home / "log" / "cli-20260531_142919.log").write_text(
        (
            "I0531 14:29:19 14328 server.go:747] "
            "Language server listening on random port at 12345 for HTTP\n"
        ),
        encoding="utf-8",
    )

    class MockResponse:
        def read(self) -> bytes:
            return json.dumps(
                {
                    "response": {
                        "buckets": [
                            {
                                "bucketId": "gemini-1.5-pro",
                                "remainingFraction": 0.25,
                                "resetTime": "2026-06-08T16:52:41Z",
                            }
                        ]
                    }
                }
            ).encode("utf-8")

        def __enter__(self) -> MockResponse:
            return self

        def __exit__(self, *args: Any) -> None:
            pass

    def mock_urlopen(*args: Any, **kwargs: Any) -> MockResponse:
        return MockResponse()

    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    provider = AntigravityProvider(str(home))
    records = provider.active_probe()
    assert len(records) == 1
    assert records[0].quota_name == "gemini-1.5-pro"
    assert records[0].remaining_percent == 25.0
    assert records[0].used_percent == 75.0
    assert records[0].resets_at == "2026-06-08T16:52:41Z"


def test_antigravity_active_probe_conn_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / ".gemini" / "antigravity-cli"
    (home / "log").mkdir(parents=True)
    (home / "log" / "cli-20260531_142919.log").write_text(
        "Language server listening on random port at 12345 for HTTP\n",
        encoding="utf-8",
    )

    def mock_urlopen(*args: Any, **kwargs: Any) -> Any:
        raise Exception("Connection refused")

    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    provider = AntigravityProvider(str(home))
    records = provider.active_probe()
    assert len(records) == 0
