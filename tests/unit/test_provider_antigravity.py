"""Tests for Antigravity CLI provider."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from quota_tracker.providers.antigravity import AntigravityProvider


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


def test_antigravity_active_probe_uses_daily_code_assist(tmp_path: Path) -> None:
    gemini_home = tmp_path / ".gemini"
    home = gemini_home / "antigravity-cli"
    home.mkdir(parents=True)
    (gemini_home / "oauth_creds.json").write_text(json.dumps({"access_token": "old"}))
    buckets = [
        {
            "model_id": "gemini-3-pro-preview",
            "token_type": "REQUESTS",
            "reset_time": "2026-06-01T00:00:00Z",
            "remaining_percent": 75.0,
            "used_percent": 25.0,
        }
    ]

    called_urls: list[str] = []

    def fake_post_json(
        url: str,
        payload: dict[str, object],
        *,
        bearer_token: str,
        timeout_seconds: int = 20,
    ) -> dict[str, object]:
        called_urls.append(url)
        assert bearer_token == "tok"
        assert "daily-cloudcode-pa.googleapis.com" in url
        return {"cloudaicompanionProject": "project-1"}

    with (
        patch("quota_tracker.providers.antigravity._get_access_token", return_value="tok"),
        patch("quota_tracker.providers.antigravity.post_json", side_effect=fake_post_json),
        patch("quota_tracker.providers.antigravity._retrieve_quota_buckets", return_value=buckets),
    ):
        records = AntigravityProvider(str(home)).active_probe()

    assert called_urls == ["https://daily-cloudcode-pa.googleapis.com/v1internal:loadCodeAssist"]
    assert len(records) == 1
    assert records[0].provider_id == "antigravity"
    assert records[0].quota_name == "gemini-3-pro-preview/REQUESTS"
    assert records[0].used_percent == 25.0
