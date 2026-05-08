"""Unit tests for Copilot provider."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from quota_tracker.core.models import SessionRecord, TokenUsageRecord
from quota_tracker.providers.copilot import CopilotProvider


@pytest.fixture
def provider() -> CopilotProvider:
    """Return a CopilotProvider instance."""
    return CopilotProvider()


@pytest.fixture
def temp_home(tmp_path: Path) -> Path:
    """Return a temporary Copilot home directory."""
    home = tmp_path / ".copilot"
    home.mkdir()
    (home / "session-state").mkdir()
    return home


def test_provider_metadata(provider: CopilotProvider) -> None:
    """Test provider metadata properties."""
    assert provider.provider_id == "copilot"
    assert provider.display_name == "Copilot"
    assert provider.default_home_path == "~/.copilot"
    assert provider.supports_active_probe is True
    assert provider.supports_passive_sync is True


def test_parse_session_file(provider: CopilotProvider, temp_home: Path) -> None:
    """Test parsing of an events.jsonl session file."""
    session_dir = temp_home / "session-state" / "test-session"
    session_dir.mkdir(parents=True)
    events_file = session_dir / "events.jsonl"

    events_file.write_text(
        json.dumps(
            {
                "type": "session.start",
                "timestamp": "2024-05-01T10:00:00Z",
                "data": {
                    "sessionId": "session-123",
                    "selectedModel": "gpt-4",
                    "startTime": "2024-05-01T10:00:00Z",
                },
            }
        )
        + "\n"
        + json.dumps(
            {
                "type": "assistant.message",
                "timestamp": "2024-05-01T10:00:10Z",
                "data": {
                    "model": "gpt-4",
                    "usage": {"inputTokens": 10, "outputTokens": 20, "totalTokens": 30},
                },
            }
        )
        + "\n"
        + json.dumps(
            {
                "type": "session.shutdown",
                "timestamp": "2024-05-01T10:05:00Z",
                "data": {
                    "modelMetrics": {
                        "gpt-4": {
                            "usage": {
                                "inputTokens": 15,
                                "outputTokens": 25,
                                "totalTokens": 40,
                            }
                        }
                    }
                },
            }
        )
        + "\n"
    )

    records = list(provider._parse_session_file(events_file))

    # SessionRecord, TokenUsageRecord (from shutdown)
    assert len(records) == 2

    session = next(r for r in records if isinstance(r, SessionRecord))
    assert session.external_session_id == "session-123"
    assert session.model_name == "gpt-4"
    assert session.metadata["shutdown_found"] is True

    usage = next(r for r in records if isinstance(r, TokenUsageRecord))
    assert usage.input_tokens == 15
    assert usage.output_tokens == 25
    assert usage.total_tokens == 40
    assert usage.model_name == "gpt-4"


@patch("urllib.request.urlopen")
def test_probe_active_weekly(
    mock_urlopen: MagicMock, provider: CopilotProvider, temp_home: Path
) -> None:
    """Test active weekly quota probing."""
    config_file = temp_home / "config.json"
    config_file.write_text(
        json.dumps(
            {
                "copilotTokens": {"github.com:user": "fake-token"},
                "lastLoggedInUser": {"host": "github.com", "login": "user"},
            }
        )
    )

    # Mock user resolution
    mock_res_user = MagicMock()
    mock_res_user.read.return_value = json.dumps(
        {"endpoints": {"api": "https://api.githubcopilot.com"}}
    ).encode("utf-8")

    # Mock chat completions
    mock_res_chat = MagicMock()
    mock_res_chat.status = 200
    mock_res_chat.headers = {
        "x-usage-ratelimit-weekly": "ent=50&rem=90&rst=2024-05-08T00:00:00Z",
        "x-quota-snapshot-chat": "ent=100&rem=50",
    }
    mock_res_chat.read.return_value = json.dumps({}).encode("utf-8")

    mock_res_user.__enter__.return_value = mock_res_user
    mock_res_chat.__enter__.return_value = mock_res_chat

    mock_urlopen.side_effect = [mock_res_user, mock_res_chat]

    records = list(provider._probe_weekly(temp_home))
    assert len(records) == 2

    weekly = next(r for r in records if r.quota_name == "weekly")
    assert weekly.remaining_percent == 90.0
    assert weekly.used_percent == 10.0

    chat = next(r for r in records if r.quota_name == "chat")
    assert chat.remaining_percent == 50.0
    assert chat.used_percent == 50.0


@patch("urllib.request.urlopen")
def test_probe_active_monthly(
    mock_urlopen: MagicMock, provider: CopilotProvider, temp_home: Path
) -> None:
    """Test active monthly entitlement probing."""
    with patch.dict("os.environ", {"COPILOT_GITHUB_COOKIE": "fake-cookie"}):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.headers = {}
        mock_response.read.return_value = json.dumps(
            {
                "quotas": {
                    "remaining": {"premiumInteractionsPercentage": 75.0},
                    "resetDate": "2024-06-01T00:00:00Z",
                }
            }
        ).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        records = list(provider._probe_monthly(temp_home))
        assert len(records) == 1
        assert records[0].quota_name == "premium_interactions"
        assert records[0].remaining_percent == 75.0
        assert records[0].used_percent == 25.0
