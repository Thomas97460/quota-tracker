"""Unit tests for record normalization logic."""

from datetime import UTC, datetime

from quota_tracker.core.models import QuotaRecord, TokenUsageRecord


def test_quota_record_normalization_used_from_remaining() -> None:
    """Test that used_percent is computed from remaining_percent."""
    record = QuotaRecord(
        provider_id="test",
        quota_name="test_quota",
        timestamp=datetime.now(UTC),
        used_percent=None,
        remaining_percent=30.0,
        window_minutes=60,
        resets_at=None,
        source="test",
    )
    assert record.used_percent == 70.0
    assert record.remaining_percent == 30.0


def test_quota_record_normalization_remaining_from_used() -> None:
    """Test that remaining_percent is computed from used_percent."""
    record = QuotaRecord(
        provider_id="test",
        quota_name="test_quota",
        timestamp=datetime.now(UTC),
        used_percent=45.0,
        remaining_percent=None,
        window_minutes=60,
        resets_at=None,
        source="test",
    )
    assert record.used_percent == 45.0
    assert record.remaining_percent == 55.0


def test_quota_record_clamping() -> None:
    """Test that percentages are clamped to [0, 100]."""
    record = QuotaRecord(
        provider_id="test",
        quota_name="test_quota",
        timestamp=datetime.now(UTC),
        used_percent=150.0,
        remaining_percent=-10.0,
        window_minutes=60,
        resets_at=None,
        source="test",
    )
    assert record.used_percent == 100.0
    assert record.remaining_percent == 0.0


def test_token_usage_total_computation() -> None:
    """Test that total_tokens is computed if not provided."""
    record = TokenUsageRecord(
        provider_id="test",
        external_session_id="s1",
        external_event_id="e1",
        timestamp=datetime.now(UTC),
        model_name="test-model",
        input_tokens=10,
        output_tokens=20,
        cached_tokens=5,
        reasoning_tokens=2,
        thoughts_tokens=1,
        tool_tokens=3,
        total_tokens=0,
    )
    assert record.total_tokens == 41


def test_token_usage_total_preserved() -> None:
    """Test that provided total_tokens is preserved even if it differs from sum."""
    record = TokenUsageRecord(
        provider_id="test",
        external_session_id="s1",
        external_event_id="e1",
        timestamp=datetime.now(UTC),
        model_name="test-model",
        input_tokens=10,
        output_tokens=20,
        total_tokens=100,
    )
    assert record.total_tokens == 100
