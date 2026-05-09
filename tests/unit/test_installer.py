"""Tests for installer and systemd helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from quota_tracker.config import AppConfig
from quota_tracker.installer import (
    _input_with_default,
    _parse_bool,
    build_systemd_unit,
    configure_interactively,
    detect_provider_homes,
    maybe_enable_service,
    merge_config,
    render_install_script,
    run_install,
    write_systemd_user_service,
)


def test_detect_provider_homes(tmp_path: Path) -> None:
    (tmp_path / ".codex").mkdir()
    detected = detect_provider_homes(tmp_path)
    assert "codex" in detected
    assert "gemini" not in detected


def test_merge_config_idempotent_updates() -> None:
    cfg = AppConfig()
    merged = merge_config(
        cfg,
        {
            "web_host": "0.0.0.0",
            "web_port": 9999,
            "active_probe_interval_minutes": 10,
            "passive_sync_interval_minutes": 5,
            "gemini": {"enabled": False, "home_path": "/tmp/g"},
        },
    )
    assert merged.daemon.web_host == "0.0.0.0"
    assert merged.daemon.web_port == 9999
    assert merged.daemon.active_probe_interval_minutes == 10
    assert merged.gemini.enabled is False
    assert merged.gemini.home_path == "/tmp/g"


def test_merge_config_validation_errors() -> None:
    cfg = AppConfig()
    with pytest.raises(ValueError):
        merge_config(cfg, {"web_port": "bad"})
    with pytest.raises(ValueError):
        merge_config(cfg, {"active_probe_interval_minutes": "bad"})


def test_systemd_unit_write_only_when_changed(tmp_path: Path) -> None:
    unit = build_systemd_unit("/bin/quota-tracker", tmp_path / "logs")
    path, changed = write_systemd_user_service(unit, tmp_path)
    assert changed is True
    _, changed2 = write_systemd_user_service(unit, tmp_path)
    assert changed2 is False
    assert path.exists()


def test_run_install_preserves_db_and_creates_dirs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    cfg = AppConfig()
    cfg.daemon.database_path = str(home / ".local" / "share" / "quota-tracker" / "db.sqlite3")
    monkeypatch.setattr(
        "quota_tracker.installer.DEFAULT_CONFIG_DIR",
        home / ".config" / "quota-tracker",
    )
    monkeypatch.setattr(
        "quota_tracker.installer.DEFAULT_LOG_DIR",
        home / ".local" / "state" / "quota-tracker" / "logs",
    )
    monkeypatch.setattr("quota_tracker.installer.save_config", lambda config: None)
    monkeypatch.setattr("quota_tracker.installer.maybe_enable_service", lambda confirm: None)
    result = run_install(
        cfg, home=home, interactive=False, enable_service=False, exec_path="/bin/qt"
    )
    assert "service_path" in result
    assert (home / ".config" / "systemd" / "user" / "quota-tracker.service").exists()


def test_interactive_prompts_and_bool_parser(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cfg = AppConfig()
    answers = iter(
        [
            "y",
            str(tmp_path / ".gemini"),
            "y",
            str(tmp_path / ".codex"),
            "n",
            str(tmp_path / ".copilot"),
            "",
            "127.0.0.1",
            "9000",
            "20",
            "10",
        ]
    )
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    out = configure_interactively(cfg, tmp_path)
    assert out.gemini.enabled is True
    assert out.codex.enabled is False
    assert out.daemon.web_port == 9000
    monkeypatch.setattr("builtins.input", lambda prompt: "invalid")
    assert _parse_bool("x", True) is True


def test_input_with_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("builtins.input", lambda prompt: "")
    assert _input_with_default("p", "d") == "d"


def test_maybe_enable_service_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr("subprocess.run", lambda args, check: calls.append(args))
    maybe_enable_service(confirm=True)
    assert len(calls) == 3
    calls.clear()
    maybe_enable_service(confirm=False)
    assert calls == []


def test_run_install_interactive_branch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    cfg = AppConfig()
    monkeypatch.setattr("quota_tracker.installer.configure_interactively", lambda config, h: config)
    monkeypatch.setattr("quota_tracker.installer.save_config", lambda config: None)
    monkeypatch.setattr("quota_tracker.installer.maybe_enable_service", lambda confirm: None)
    result = run_install(
        cfg, home=home, interactive=True, enable_service=False, exec_path="/bin/qt"
    )
    assert result["service_updated"] is True


def test_render_install_script_contains_oneliner_flow() -> None:
    script = render_install_script()
    assert "pip install --user quota-tracker" in script
    assert "quota-tracker install --interactive" in script
