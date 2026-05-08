"""Unit tests for Gemini provider."""

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from quota_tracker.providers.gemini import GeminiProvider


@pytest.fixture
def gemini_home(tmp_path: Path) -> Path:
    """Create a temporary Gemini home directory for testing."""
    home = tmp_path / ".gemini"
    home.mkdir()
    return home


def test_gemini_probe_active(gemini_home: Path) -> None:
    """Test active quota probing with mocked network calls."""
    oauth_creds = gemini_home / "oauth_creds.json"
    oauth_creds.write_text(
        json.dumps(
            {"access_token": "fake-token", "expiry_date": (time.time() + 3600) * 1000}
        )
    )

    provider = GeminiProvider()

    with patch("urllib.request.urlopen") as mock_urlopen:
        # Mock responses
        res1 = MagicMock()
        res1.read.return_value = json.dumps(
            {"cloudaicompanionProject": "my-project-123"}
        ).encode("utf-8")
        res1.__enter__.return_value = res1

        res2 = MagicMock()
        res2.read.return_value = json.dumps(
            {
                "buckets": [
                    {
                        "modelId": "gemini-1.5-pro",
                        "tokenType": "input",
                        "remainingFraction": 0.8,
                        "resetTime": "2024-05-01T12:00:00Z",
                    }
                ]
            }
        ).encode("utf-8")
        res2.__enter__.return_value = res2

        mock_urlopen.side_effect = [res1, res2]

        records = list(provider.probe_active(str(gemini_home)))

        assert len(records) == 1
        record = records[0]
        assert record.provider_id == "gemini"
        assert record.quota_name == "gemini-1.5-pro:input"
        assert record.remaining_percent == 80.0
        assert record.used_percent == 20.0
        assert record.resets_at == datetime(2024, 5, 1, 12, 0, tzinfo=UTC)


def test_gemini_probe_active_refresh_token(gemini_home: Path) -> None:
    """Test active quota probing with token refresh."""
    oauth_creds = gemini_home / "oauth_creds.json"
    oauth_creds.write_text(
        json.dumps(
            {
                "access_token": "expired-token",
                "refresh_token": "my-refresh-token",
                "expiry_date": (time.time() - 3600) * 1000,
            }
        )
    )

    provider = GeminiProvider()

    with patch("urllib.request.urlopen") as mock_urlopen:
        # 1. Refresh token call
        res_refresh = MagicMock()
        res_refresh.read.return_value = json.dumps(
            {"access_token": "new-token"}
        ).encode("utf-8")
        res_refresh.__enter__.return_value = res_refresh

        # 2. loadCodeAssist
        res1 = MagicMock()
        res1.read.return_value = json.dumps(
            {"cloudaicompanionProject": "my-project-123"}
        ).encode("utf-8")
        res1.__enter__.return_value = res1

        # 3. retrieveUserQuota
        res2 = MagicMock()
        res2.read.return_value = json.dumps({"buckets": []}).encode("utf-8")
        res2.__enter__.return_value = res2

        mock_urlopen.side_effect = [res_refresh, res1, res2]

        list(provider.probe_active(str(gemini_home)))

        # Verify calls
        assert mock_urlopen.call_count == 3
        # Check refresh call
        args, _kwargs = mock_urlopen.call_args_list[0]
        req = args[0]
        assert req.full_url == "https://oauth2.googleapis.com/token"
        assert b"refresh_token=my-refresh-token" in req.data
