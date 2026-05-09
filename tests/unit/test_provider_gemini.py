"""Gemini provider tests."""

import json
from pathlib import Path

from quota_tracker.providers.gemini import GeminiProvider


def test_gemini_passive_and_incremental(tmp_path: Path) -> None:
    chats = tmp_path / "tmp" / "a" / "chats"
    chats.mkdir(parents=True)
    f = chats / "s1.jsonl"
    f.write_text(
        json.dumps({"timestamp": "2026-01-01T00:00:00+00:00", "tokens": {"input": 1}}) + "\n"
    )
    p = GeminiProvider(str(tmp_path))
    full = p.passive_scan_full()
    assert len(full.sessions) == 1
    assert full.parse_failures == 0
    inc = p.passive_scan_incremental(full.high_water_marks)
    assert len(inc.sessions) == 0


def test_gemini_json_parse_paths_and_failures(tmp_path: Path) -> None:
    chats = tmp_path / "x" / "chats"
    chats.mkdir(parents=True)
    (chats / "bad.jsonl").write_text("\n{bad}\n")
    (chats / "list.json").write_text(json.dumps([{"timestamp": "2026-01-01T00:00:00+00:00"}]))
    (chats / "dict.json").write_text(
        json.dumps({"events": [{"timestamp": "2026-01-01T00:00:01+00:00"}]})
    )
    (chats / "broken.json").write_text("{bad")
    p = GeminiProvider(str(tmp_path))
    result = p.passive_scan_full()
    assert result.parse_failures >= 2


def test_gemini_active_probe_paths(tmp_path: Path) -> None:
    p = GeminiProvider(str(tmp_path), active_probe_enabled=False)
    assert p.active_probe() == []

    p2 = GeminiProvider(str(tmp_path), active_probe_enabled=True)
    assert p2.active_probe() == []  # no oauth_creds.json

    (tmp_path / "oauth_creds.json").write_text("{}")
    assert p2.active_probe() == []  # creds exist but no token or refresh_token
