"""Tests for CLI host and port override."""

from __future__ import annotations

import pytest
import uvicorn

from quota_tracker import cli
from quota_tracker.config import AppConfig


class _FakeService:
    def __init__(self, **kwargs: object) -> None:
        pass

    def migrate_and_prepare(self) -> None:
        pass

    def start_scheduler(self) -> None:
        pass

    def stop_scheduler(self) -> None:
        pass


def test_cli_daemon_host_port_override(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_host = None
    captured_port = None

    def fake_run(app, host, port):
        nonlocal captured_host, captured_port
        captured_host = host
        captured_port = port

    monkeypatch.setattr(cli, "DaemonService", _FakeService)
    monkeypatch.setattr("quota_tracker.cli.load_config", lambda: AppConfig())
    monkeypatch.setattr(uvicorn, "run", fake_run)

    # Test default
    monkeypatch.setattr("sys.argv", ["quota-tracker", "daemon"])
    assert cli.main() == 0
    assert captured_host == "127.0.0.1"
    assert captured_port == 8787

    # Test override
    monkeypatch.setattr(
        "sys.argv", ["quota-tracker", "daemon", "--host", "0.0.0.0", "--port", "9999"]
    )
    assert cli.main() == 0
    assert captured_host == "0.0.0.0"
    assert captured_port == 9999

    # Test invalid port
    monkeypatch.setattr("sys.argv", ["quota-tracker", "daemon", "--port", "70000"])
    assert cli.main() == 2


def test_cli_serve_host_port_override(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_host = None
    captured_port = None

    def fake_run(app, host, port):
        nonlocal captured_host, captured_port
        captured_host = host
        captured_port = port

    monkeypatch.setattr("quota_tracker.cli.load_config", lambda: AppConfig())
    monkeypatch.setattr(uvicorn, "run", fake_run)

    # Test default
    monkeypatch.setattr("sys.argv", ["quota-tracker", "serve"])
    assert cli.main() == 0
    assert captured_host == "127.0.0.1"
    assert captured_port == 8787

    # Test override
    monkeypatch.setattr(
        "sys.argv", ["quota-tracker", "serve", "--host", "10.0.0.1", "--port", "1234"]
    )
    assert cli.main() == 0
    assert captured_host == "10.0.0.1"
    assert captured_port == 1234
