"""Unit tests for Codex provider."""

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from quota_tracker.core.models import QuotaRecord, SessionRecord, TokenUsageRecord
from quota_tracker.providers.codex import CodexProvider


@pytest.fixture
def provider() -> CodexProvider:
    """Return a CodexProvider instance."""
    return CodexProvider()


@pytest.fixture
def temp_home(tmp_path: Path) -> Path:
    """Return a temporary Codex home directory."""
    home = tmp_path / ".codex"
    home.mkdir()
    (home / "sessions").mkdir()
    (home / "archived_sessions").mkdir()
    return home


def test_provider_metadata(provider: CodexProvider) -> None:
    """Test provider metadata properties."""
    assert provider.provider_id == "codex"
    assert provider.display_name == "Codex"
    assert provider.default_home_path == "~/.codex"
    assert provider.supports_active_probe is True
    assert provider.supports_passive_sync is True


def test_parse_session_file(provider: CodexProvider, temp_home: Path) -> None:
    """Test parsing of a JSONL session file."""
    session_file = temp_home / "sessions" / "test.jsonl"
    session_file.write_text(
        json.dumps(
            {
                "type": "session_meta",
                "timestamp": "2024-05-01T10:00:00Z",
                "payload": {
                    "id": "session-123",
                    "cwd": "/project",
                    "cli_version": "0.1.0",
                },
            }
        )
        + "\n"
        + json.dumps(
            {
                "type": "turn_context",
                "timestamp": "2024-05-01T10:00:01Z",
                "payload": {"model": "gpt-4"},
            }
        )
        + "\n"
        + json.dumps(
            {
                "type": "event_msg",
                "timestamp": "2024-05-01T10:00:05Z",
                "payload": {
                    "type": "token_count",
                    "info": {
                        "last_token_usage": {
                            "input_tokens": 10,
                            "output_tokens": 20,
                            "total_tokens": 30,
                        }
                    },
                    "rate_limits": {
                        "primary": {
                            "used_percent": 45,
                            "window_minutes": 60,
                            "resets_at": 1714557600,
                        }
                    },
                },
            }
        )
        + "\n"
    )

    records = list(provider._parse_session_file(session_file))

    # SessionRecord, TokenUsageRecord, QuotaRecord
    assert len(records) == 3

    session = next(r for r in records if isinstance(r, SessionRecord))
    assert session.external_session_id == "session-123"
    assert session.model_name == "gpt-4"
    assert session.project_path == "/project"
    assert session.metadata["cli_version"] == "0.1.0"

    usage = next(r for r in records if isinstance(r, TokenUsageRecord))
    assert usage.input_tokens == 10
    assert usage.output_tokens == 20
    assert usage.total_tokens == 30

    quota = next(r for r in records if isinstance(r, QuotaRecord))
    assert quota.quota_name == "primary"
    assert quota.used_percent == 45.0


@patch("urllib.request.urlopen")
def test_probe_active(
    mock_urlopen: MagicMock, provider: CodexProvider, temp_home: Path
) -> None:
    """Test active quota probing."""
    auth_file = temp_home / "auth.json"
    auth_file.write_text(json.dumps({"tokens": {"access_token": "fake-token"}}))

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(
        {
            "rate_limit": {
                "primary_window": {
                    "used_percent": 12.5,
                    "limit_window_seconds": 3600,
                    "reset_after_seconds": 600,
                }
            }
        }
    ).encode("utf-8")
    mock_response.__enter__.return_value = mock_response
    mock_urlopen.return_value = mock_response

    records = list(provider.probe_active(str(temp_home)))
    assert len(records) == 1
    assert isinstance(records[0], QuotaRecord)
    assert records[0].quota_name == "primary"
    assert records[0].used_percent == 12.5
    assert records[0].source == "active_probe"


def test_sync_state_db(provider: CodexProvider, temp_home: Path) -> None:
    """Test syncing from state_5.sqlite."""
    db_path = temp_home / "state_5.sqlite"
    con = sqlite3.connect(db_path)
    con.execute(
        """
        CREATE TABLE threads (
            id TEXT PRIMARY KEY,
            created_at INTEGER,
            updated_at INTEGER,
            model TEXT,
            tokens_used INTEGER,
            cwd TEXT,
            title TEXT,
            cli_version TEXT
        )
    """
    )
    con.execute(
        """
        INSERT INTO threads (
            id, created_at, updated_at, model, tokens_used, cwd, title, cli_version
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            "thread-1",
            1714557600,
            1714557660,
            "gpt-4",
            150,
            "/home/user/project",
            "My Thread",
            "0.1.0",
        ),
    )

    con.commit()
    con.close()

    records = list(provider._sync_state_db(temp_home))
    assert len(records) == 2  # SessionRecord and TokenUsageRecord

    session = next(r for r in records if isinstance(r, SessionRecord))
    assert session.external_session_id == "thread-1"
    assert session.model_name == "gpt-4"
    assert session.project_path == "/home/user/project"

    usage = next(r for r in records if isinstance(r, TokenUsageRecord))
    assert usage.total_tokens == 150
    assert usage.model_name == "gpt-4"


def test_scan_incremental(provider: CodexProvider, temp_home: Path) -> None:
    """Test incremental scanning."""
    session_file = temp_home / "sessions" / "test.jsonl"
    session_file.write_text(
        json.dumps(
            {
                "type": "session_meta",
                "timestamp": "2024-05-01T10:00:00Z",
                "payload": {"id": "s1"},
            }
        )
        + "\n"
    )

    stat = session_file.stat()
    sync_state = {str(session_file): {"mtime": stat.st_mtime, "size": stat.st_size}}

    records = list(provider.scan_incremental(str(temp_home), sync_state))
    assert len(records) == 0  # No changes

    # Modify file
    session_file.write_text(
        session_file.read_text()
        + json.dumps({"type": "turn_context", "payload": {"model": "gpt-4"}})
        + "\n"
    )

    records = list(provider.scan_incremental(str(temp_home), sync_state))
    assert len(records) > 0
    assert sync_state[str(session_file)]["size"] > stat.st_size


def test_sync_logs_db(provider: CodexProvider, temp_home: Path) -> None:
    """Test syncing from logs_2.sqlite."""
    db_path = temp_home / "logs_2.sqlite"
    con = sqlite3.connect(db_path)
    con.execute(
        """
        CREATE TABLE logs (
            id INTEGER PRIMARY KEY,
            ts INTEGER,
            feedback_log_body TEXT
        )
    """
    )

    body = "Received message " + json.dumps(
        {
            "type": "response.completed",
            "conversation_id": "conv-1",
            "response": {
                "model": "gpt-4o",
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "total_tokens": 150,
                },
            },
        }
    )

    con.execute(
        "INSERT INTO logs (ts, feedback_log_body) VALUES (?, ?)", (1714557600, body)
    )
    con.commit()
    con.close()

    records = list(provider._sync_logs_db(temp_home))
    assert len(records) == 1
    usage = records[0]
    assert isinstance(usage, TokenUsageRecord)
    assert usage.model_name == "gpt-4o"
    assert usage.total_tokens == 150
    assert usage.input_tokens == 100
    assert usage.output_tokens == 50
