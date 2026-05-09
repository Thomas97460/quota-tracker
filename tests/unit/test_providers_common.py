"""Tests for provider contract and normalization."""

from quota_tracker.providers import normalize_quota, normalize_session, normalize_token_usage


def test_normalize_session_defaults() -> None:
    s = normalize_session("codex", "x", None, None, None, None, None, {})
    assert s.model_name == "unknown"
    assert s.project_path is None


def test_normalize_token_usage_defaults_and_total_compute() -> None:
    t = normalize_token_usage(
        "codex", "s", "e", "2026-01-01T00:00:00+00:00", None, {}, input_tokens=1
    )
    assert t["output_tokens"] == 0
    assert t["total_tokens"] == 1


def test_normalize_quota_compute_and_clamp() -> None:
    q = normalize_quota(
        "gemini", "default", "2026-01-01T00:00:00+00:00", "active_probe", {}, remaining_percent=120
    )
    assert q.remaining_percent == 100.0
    assert q.used_percent == 0.0

    q2 = normalize_quota(
        "gemini", "default", "2026-01-01T00:00:00+00:00", "active_probe", {}, used_percent=20
    )
    assert q2.remaining_percent == 80.0
