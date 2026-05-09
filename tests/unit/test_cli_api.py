"""Tests for CLI and API behavior."""

from __future__ import annotations

from pathlib import Path

import pytest
import uvicorn
from fastapi.testclient import TestClient

from quota_tracker import api, cli
from quota_tracker.config import AppConfig
from quota_tracker.config import load_config as load_config_from_path
from quota_tracker.config import save_config as save_to_path


class _FakeSummary:
    def __init__(self) -> None:
        self.sessions_upserted = 1
        self.token_rows_inserted = 2
        self.quota_rows_inserted = 3
        self.parse_failures = 0
        self.failed_providers: list[str] = []


class _FakeService:
    def __init__(self, db_path: str, **kwargs: object) -> None:
        self.db_path = db_path

    def migrate_and_prepare(self) -> None:
        return None

    def run_scan(self, provider: str = "all", full: bool = False) -> _FakeSummary:
        assert provider in {"all", "gemini", "codex", "copilot"}
        assert isinstance(full, bool)
        return _FakeSummary()

    def run_probe(self, provider: str = "all") -> _FakeSummary:
        assert provider in {"all", "gemini", "codex", "copilot"}
        return _FakeSummary()

    def start_scheduler(self) -> None:
        return None

    def stop_scheduler(self) -> None:
        return None

    def set_provider_enabled(self, provider_id: str, enabled: bool) -> None:
        assert provider_id in {"gemini", "codex", "copilot"}
        assert enabled is True

    def reset_high_water_marks(self, provider_id: str) -> None:
        assert provider_id in {"gemini", "codex", "copilot"}


def test_cli_config_and_default(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.argv", ["quota-tracker"])
    assert cli.main() == 0
    out = capsys.readouterr().out
    assert "daemon" in out


def test_cli_config_path(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.argv", ["quota-tracker", "config-path"])
    assert cli.main() == 0
    out = capsys.readouterr().out
    assert "config.json" in out


def test_cli_show_default_config_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.argv", ["quota-tracker", "show-default-config"])
    assert cli.main() == 0
    assert "daemon" in capsys.readouterr().out


def test_cli_unknown_command(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["quota-tracker", "unknown"])
    assert cli.main() == 2


def test_cli_helper_branches() -> None:
    assert cli._parse_bool(None) is None
    cli._validate_port(None)


def test_cli_config_show_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config_path = tmp_path / "config.json"
    monkeypatch.setattr(
        "quota_tracker.cli.load_config", lambda: load_config_from_path(str(config_path))
    )
    monkeypatch.setattr(
        "quota_tracker.cli.save_config", lambda cfg: save_to_path(cfg, str(config_path))
    )

    monkeypatch.setattr("sys.argv", ["quota-tracker", "config", "show"])
    assert cli.main() == 0
    assert "daemon" in capsys.readouterr().out

    monkeypatch.setattr(
        "sys.argv",
        [
            "quota-tracker",
            "config",
            "set",
            "--provider",
            "gemini",
            "--enabled",
            "false",
            "--home-path",
            str(tmp_path / "g"),
            "--active-probe-interval-minutes",
            "30",
            "--passive-sync-interval-minutes",
            "10",
            "--host",
            "127.0.0.1",
            "--port",
            "9999",
            "--database-path",
            str(tmp_path / "db.sqlite3"),
            "--log-level",
            "DEBUG",
            "--active-probe-enabled",
            "true",
            "--passive-sync-enabled",
            "false",
        ],
    )
    assert cli.main() == 0
    out = capsys.readouterr().out
    assert '"enabled": false' in out

    monkeypatch.setattr(
        "sys.argv",
        [
            "quota-tracker",
            "config",
            "set",
            "--active-probe-interval-minutes",
            "0",
        ],
    )
    assert cli.main() == 2
    assert "must be > 0" in capsys.readouterr().out

    monkeypatch.setattr(
        "sys.argv",
        [
            "quota-tracker",
            "config",
            "set",
            "--port",
            "70000",
        ],
    )
    assert cli.main() == 2
    assert "port must be in [1, 65535]" in capsys.readouterr().out


def test_cli_scan_probe_and_full_rescan(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "DaemonService", _FakeService)
    monkeypatch.setattr("quota_tracker.cli.load_config", lambda: AppConfig())

    monkeypatch.setattr("sys.argv", ["quota-tracker", "scan", "--provider", "gemini", "--full"])
    assert cli.main() == 0
    assert "sessions_upserted=1" in capsys.readouterr().out

    monkeypatch.setattr("sys.argv", ["quota-tracker", "probe", "--provider", "codex"])
    assert cli.main() == 0
    assert "quota_rows_inserted=3" in capsys.readouterr().out

    monkeypatch.setattr(
        "sys.argv", ["quota-tracker", "probe", "--provider", "copilot", "--dry-run"]
    )
    assert cli.main() == 0
    assert "dry-run" in capsys.readouterr().out


def test_cli_daemon_serve_and_set_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "DaemonService", _FakeService)
    monkeypatch.setattr("quota_tracker.cli.load_config", lambda: AppConfig())
    monkeypatch.setattr(uvicorn, "run", lambda app, host, port: None)

    monkeypatch.setattr("sys.argv", ["quota-tracker", "daemon"])
    assert cli.main() == 0

    monkeypatch.setattr("sys.argv", ["quota-tracker", "serve"])
    assert cli.main() == 0


def test_cli_config_unknown_subcommand(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["quota-tracker", "config"])
    assert cli.main() == 2


def test_health_endpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = api.create_app(db_path=tmp_path / "api.sqlite3")
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["database"]["migrated"] is True
    assert payload["scheduler"]["enabled"] is False
    assert len(payload["providers"]) == 3


def test_cli_migrate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cfg = AppConfig()
    cfg.daemon.database_path = str(tmp_path / "migrate.sqlite3")
    monkeypatch.setattr("quota_tracker.cli.load_config", lambda: cfg)
    monkeypatch.setattr("sys.argv", ["quota-tracker", "migrate"])
    assert cli.main() == 0
    assert "migrate.sqlite3" in capsys.readouterr().out


def test_python_m_quota_tracker_entrypoint(monkeypatch: pytest.MonkeyPatch) -> None:
    import runpy

    monkeypatch.setattr("sys.argv", ["quota-tracker", "show-default-config"])
    with pytest.raises(SystemExit) as exc_info:
        runpy.run_module("quota_tracker", run_name="__main__")
    assert exc_info.value.code == 0


def test_cli_install_commands(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("quota_tracker.cli.load_config", lambda: AppConfig())
    monkeypatch.setattr(
        "quota_tracker.cli.run_install",
        lambda config, home, interactive, enable_service, exec_path: {
            "service_path": "/tmp/quota-tracker.service",
            "service_updated": exec_path == "/bin/quota-tracker",
        },
    )
    monkeypatch.setattr(
        "quota_tracker.cli.render_install_script",
        lambda: "set -eu\nquota-tracker install --interactive\n",
    )

    monkeypatch.setattr(
        "sys.argv",
        ["quota-tracker", "install", "--interactive", "--exec-path", "/bin/quota-tracker"],
    )
    assert cli.main() == 0
    assert "service_path=" in capsys.readouterr().out

    monkeypatch.setattr(
        "sys.argv",
        ["quota-tracker", "install-user-service", "--exec-path", "/bin/quota-tracker"],
    )
    assert cli.main() == 0
    assert "updated=True" in capsys.readouterr().out

    monkeypatch.setattr("sys.argv", ["quota-tracker", "install-script"])
    assert cli.main() == 0
    assert "install --interactive" in capsys.readouterr().out
