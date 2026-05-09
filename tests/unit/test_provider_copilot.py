"""Copilot provider tests."""

import json
from pathlib import Path

from quota_tracker.providers.copilot import CopilotProvider


def test_copilot_passive_and_incremental(tmp_path: Path) -> None:
    d = tmp_path / "session-state" / "abc"
    d.mkdir(parents=True)
    f = d / "events.jsonl"
    f.write_text(
        "\n".join(
            [
                json.dumps({"timestamp": "2026-01-01T00:00:00+00:00", "model": "gpt-4.1"}),
                json.dumps(
                    {"timestamp": "2026-01-01T00:01:00+00:00", "metrics": {"latencyMs": 12}}
                ),
                json.dumps(
                    {
                        "timestamp": "2026-01-01T00:02:00+00:00",
                        "type": "assistant.message",
                        "modelName": "gpt-4.1",
                        "usage": {
                            "inputTokens": 10,
                            "outputTokens": 20,
                            "cacheReadTokens": 3,
                            "reasoningTokens": 4,
                            "totalTokens": 37,
                        },
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-01-01T00:03:00+00:00",
                        "type": "session.shutdown",
                        "input_tokens": 5,
                        "output_tokens": 7,
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-01-01T00:04:00+00:00",
                        "type": "session.shutdown",
                        "data": {
                            "modelMetrics": {
                                "gpt-5.3-codex": {
                                    "usage": {
                                        "inputTokens": 18,
                                        "outputTokens": 6,
                                        "cacheReadTokens": 8,
                                        "reasoningTokens": 3,
                                    }
                                }
                            }
                        },
                    }
                ),
            ]
        )
        + "\n"
    )
    p = CopilotProvider(str(tmp_path))
    r1 = p.passive_scan_full()
    assert len(r1.sessions) == 1
    assert len(r1.token_usage) == 3
    assert r1.token_usage[0]["provider_id"] == "copilot"
    assert r1.token_usage[0]["external_session_id"] == "abc"
    assert r1.token_usage[0]["input_tokens"] == 10
    assert r1.token_usage[0]["output_tokens"] == 20
    assert r1.token_usage[0]["cached_tokens"] == 3
    assert r1.token_usage[0]["reasoning_tokens"] == 4
    assert r1.token_usage[0]["total_tokens"] == 37
    assert r1.token_usage[1]["total_tokens"] == 12
    assert r1.token_usage[2]["model_name"] == "gpt-5.3-codex"
    assert r1.token_usage[2]["total_tokens"] == 35
    r2 = p.passive_scan_incremental(r1.high_water_marks)
    assert len(r2.sessions) == 0
    assert len(r2.token_usage) == 0


def test_copilot_passive_parse_failure(tmp_path: Path) -> None:
    d = tmp_path / "session-state" / "abc"
    d.mkdir(parents=True)
    (d / "events.jsonl").write_text("\n{bad}\n")
    p = CopilotProvider(str(tmp_path))
    r = p.passive_scan_full()
    assert r.parse_failures == 1


def test_copilot_header_parsing_full_and_weekly_only() -> None:
    ts = "2026-01-01T00:00:00+00:00"
    out = CopilotProvider.parse_quota_headers(
        {
            "x-usage-ratelimit-weekly": "rem=90&rst=2026-12-01T00:00:00Z",
            "x-usage-ratelimit-session": "ok",
            "x-quota-snapshot-chat": "ok",
            "x-quota-snapshot-completions": "ok",
            "x-quota-snapshot-premium_interactions": "ok",
        },
        ts,
    )
    assert len(out) == 5
    assert out[0].quota_name == "weekly"
    assert out[0].used_percent == 10.0

    weekly_only = CopilotProvider.parse_quota_headers({"x-usage-ratelimit-weekly": "rem=50"}, ts)
    assert weekly_only[0].resets_at is None


def test_copilot_active_probe_paths(tmp_path: Path) -> None:
    p = CopilotProvider(str(tmp_path))
    assert p.active_probe() == []  # no config.json

    (tmp_path / "config.json").write_text("{}")
    assert p.active_probe() == []  # config exists but no copilotTokens
