"""Codex provider tests."""

import json
import sqlite3
from pathlib import Path

from quota_tracker.providers.codex import CodexProvider


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
                        "model": "gpt-5",
                        "timestamp": "2026-01-01T00:00:01+00:00",
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
    assert r.token_usage[1]["model_name"] == "GPT-5.3-Codex-Spark"
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


def test_codex_active_probe_paths(tmp_path: Path) -> None:
    p = CodexProvider(str(tmp_path), active_probe_enabled=False)
    assert p.active_probe() == []

    p2 = CodexProvider(str(tmp_path), active_probe_enabled=True)
    assert p2.active_probe() == []

    (tmp_path / "auth.json").write_text("{}")
    out = p2.active_probe()
    assert len(out) == 1
    assert out[0].quota_name == "primary"
