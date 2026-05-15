"""Copilot provider tests."""

import json
from pathlib import Path

import pytest

from quota_tracker.providers import copilot as copilot_mod
from quota_tracker.providers.copilot import CopilotProbeError, CopilotProvider


def test_copilot_passive_and_incremental(tmp_path: Path) -> None:
    d = tmp_path / "session-state" / "abc"
    d.mkdir(parents=True)
    f = d / "events.jsonl"
    f.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "session.start",
                        "timestamp": "2026-01-01T00:00:00+00:00",
                        "data": {"context": {"cwd": "/tmp/repo"}},
                    }
                ),
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
    assert r1.sessions[0].project_path == "/tmp/repo"
    assert r1.sessions[0].project_name == "repo"
    assert len(r1.token_usage) == 3
    assert r1.token_usage[0]["provider_id"] == "copilot"
    assert r1.token_usage[0]["external_session_id"] == "abc"
    assert r1.token_usage[0]["input_tokens"] == 7
    assert r1.token_usage[0]["output_tokens"] == 20
    assert r1.token_usage[0]["cached_tokens"] == 3
    assert r1.token_usage[0]["reasoning_tokens"] == 4
    assert r1.token_usage[0]["total_tokens"] == 37
    assert r1.token_usage[1]["total_tokens"] == 12
    assert r1.token_usage[2]["model_name"] == "gpt-5.3-codex"
    assert r1.token_usage[2]["total_tokens"] == 27
    old_mark = {
        str(f): {
            "path": str(f),
            "size": f.stat().st_size,
            "mtime": f.stat().st_mtime,
            "last_event_ts": None,
        }
    }
    backfill = p.passive_scan_incremental(old_mark)
    assert len(backfill.sessions) == 1
    assert backfill.sessions[0].project_path == "/tmp/repo"
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


def test_copilot_active_probe_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = CopilotProvider(str(tmp_path))
    monkeypatch.delenv("COPILOT_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(copilot_mod, "_token_from_gh_cli", lambda: None)
    monkeypatch.setattr(copilot_mod, "_token_from_gh_hosts_yml", lambda: None)
    with pytest.raises(CopilotProbeError, match="No Copilot auth token found"):
        p.active_probe()

    cfg = {
        "copilotTokens": {"github.com:octocat": "token-from-config"},
        "lastLoggedInUser": {"host": "github.com", "login": "octocat"},
    }
    (tmp_path / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    assert copilot_mod._copilot_config_token(tmp_path) == "token-from-config"


def test_copilot_token_resolution_prefers_provider_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = {
        "copilotTokens": {"github.com:octocat": "token-from-config"},
        "lastLoggedInUser": {"host": "github.com", "login": "octocat"},
    }
    (tmp_path / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    monkeypatch.setenv("GH_TOKEN", "token-from-env")
    assert copilot_mod._copilot_config_token(tmp_path) == "token-from-config"


def test_copilot_token_resolution_requires_last_logged_in_user(tmp_path: Path) -> None:
    cfg = {
        "copilotTokens": {"github.com:octocat": "token-from-config"},
    }
    (tmp_path / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    assert copilot_mod._copilot_config_token(tmp_path) is None


def test_copilot_token_resolution_env_fallback_without_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GH_TOKEN", "token-from-env")
    assert copilot_mod._copilot_config_token(Path("/path/that/does/not/exist")) is None
    assert (
        copilot_mod._copilot_config_token(
            Path("/path/that/does/not/exist"), allow_global_fallback=True
        )
        == "token-from-env"
    )


def test_copilot_token_resolution_hosts_yml_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("COPILOT_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(copilot_mod, "_token_from_gh_cli", lambda: None)

    gh_dir = tmp_path / "gh"
    gh_dir.mkdir()
    (gh_dir / "hosts.yml").write_text(
        "github.com:\n  user: capyBearista\n  oauth_token: token-from-hosts\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("GH_CONFIG_DIR", str(gh_dir))

    assert copilot_mod._copilot_config_token(tmp_path) is None
    assert (
        copilot_mod._copilot_config_token(tmp_path, allow_global_fallback=True)
        == "token-from-hosts"
    )


def test_copilot_active_probe_custom_home_ignores_global_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    custom_home = tmp_path / "copilot-home"
    custom_home.mkdir()
    p = CopilotProvider(str(custom_home))
    monkeypatch.setenv("GH_TOKEN", "token-from-env")
    with pytest.raises(CopilotProbeError, match="No Copilot auth token found"):
        p.active_probe()


def test_copilot_active_probe_default_home_disables_global_fallback_without_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    p = CopilotProvider("~/.copilot")
    monkeypatch.delenv("QUOTA_TRACKER_COPILOT_ALLOW_GLOBAL_AUTH_FALLBACK", raising=False)
    monkeypatch.setenv("GH_TOKEN", "token-from-env")
    monkeypatch.setattr(copilot_mod, "_token_from_copilot_config", lambda _home: None)
    with pytest.raises(CopilotProbeError, match="No Copilot auth token found"):
        p.active_probe()


def test_copilot_active_probe_http_error_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = CopilotProvider(str(tmp_path))
    monkeypatch.setattr(copilot_mod, "_copilot_config_token", lambda *_args, **_kwargs: "token")
    monkeypatch.setattr(
        copilot_mod, "_resolve_copilot_api_url", lambda _token: "https://api.example"
    )
    monkeypatch.setattr(
        copilot_mod,
        "request_with_response_headers",
        lambda *_args, **_kwargs: (401, {}, "{}"),
    )

    with pytest.raises(CopilotProbeError, match="HTTP 401"):
        p.active_probe()


def test_copilot_active_probe_missing_quota_headers_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = CopilotProvider(str(tmp_path))
    monkeypatch.setattr(copilot_mod, "_copilot_config_token", lambda *_args, **_kwargs: "token")
    monkeypatch.setattr(
        copilot_mod, "_resolve_copilot_api_url", lambda _token: "https://api.example"
    )
    monkeypatch.setattr(
        copilot_mod,
        "request_with_response_headers",
        lambda *_args, **_kwargs: (200, {"content-type": "application/json"}, "{}"),
    )

    with pytest.raises(CopilotProbeError, match="no quota headers"):
        p.active_probe()
