"""Tests for installer and systemd helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from quota_tracker.config import AppConfig
from quota_tracker.db import apply_migrations, connect_db, get_provider_row, update_provider_row
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
    sync_provider_rows_from_config,
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
    cfg.codex.enabled = False
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
    conn = connect_db(cfg.daemon.database_path)
    try:
        row = get_provider_row(conn, "codex")
        assert row is not None
        assert row["enabled"] is False
    finally:
        conn.close()


def test_interactive_prompts_and_bool_parser(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """New flow: 4 providers × (enable + home_path) + 3 daemon prompts + final confirm.

    Providers: gemini (enabled=y), codex (enabled=n, no home prompt), copilot (enabled=y),
               claude (enabled=n, not detected → no home prompt)
    gemini, codex, copilot detected; claude NOT detected (default_enabled=False).
    prompt order per provider: enable?, home_path (only if enabled)
    gemini:  enable=y  home=<path>
    codex:   enable=n  (no home prompt)
    copilot: enable=y  home=<path>
    claude:  enable=n  (not detected, default=False → no home prompt)
    daemon:  web_host, web_port, sync_interval_minutes
    confirm: y
    """
    monkeypatch.setenv("NO_COLOR", "1")

    (tmp_path / ".gemini").mkdir()
    (tmp_path / ".codex").mkdir()
    (tmp_path / ".copilot").mkdir()
    # .claude NOT created → claude not detected → default_enabled=False

    gemini_path = str(tmp_path / ".gemini")
    copilot_path = str(tmp_path / ".copilot")

    answers = iter(
        [
            "y",  # enable gemini
            gemini_path,  # gemini home path
            "n",  # enable codex (disabled → no home prompt)
            "y",  # enable copilot
            copilot_path,  # copilot home path
            "n",  # enable claude (not detected → no home prompt)
            "127.0.0.1",  # web host
            "9000",  # web port
            "5",  # sync interval minutes
            "y",  # final confirm
        ]
    )
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))

    cfg = AppConfig()
    out = configure_interactively(cfg, tmp_path)
    assert out.gemini.enabled is True
    assert out.codex.enabled is False
    assert out.copilot.enabled is True
    assert out.claude.enabled is False
    assert out.daemon.web_port == 9000

    # _parse_bool falls back to default on invalid input
    monkeypatch.setattr("builtins.input", lambda prompt: "invalid")
    assert _parse_bool("x", True) is True


def test_input_with_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
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


def test_sync_provider_rows_preserves_runtime_safe_options(tmp_path: Path) -> None:
    db_path = tmp_path / "quota.sqlite3"
    cfg = AppConfig()
    cfg.daemon.database_path = str(db_path)
    cfg.gemini.enabled = False
    cfg.gemini.home_path = str(tmp_path / "gemini-home")
    conn = connect_db(str(db_path))
    try:
        apply_migrations(conn)
        row = get_provider_row(conn, "gemini")
        assert row is not None
        db_cfg = dict(row["config"])
        db_cfg["safe_options"] = {"last_successful_probe_at": "2026-01-01T00:00:00+00:00"}
        update_provider_row(conn, "gemini", enabled=True, config=db_cfg)
        conn.commit()
    finally:
        conn.close()

    sync_provider_rows_from_config(cfg)

    conn = connect_db(str(db_path))
    try:
        row = get_provider_row(conn, "gemini")
        assert row is not None
        assert row["enabled"] is False
        assert row["config"]["home_path"] == str(tmp_path / "gemini-home")
        assert row["config"]["safe_options"]["last_successful_probe_at"].startswith("2026")
    finally:
        conn.close()


def test_interactive_undetected_provider(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Ensure error_mark branch runs when a provider is not detected."""
    monkeypatch.setenv("NO_COLOR", "1")
    # Only gemini directory exists — codex, copilot, and claude are NOT detected
    (tmp_path / ".gemini").mkdir()

    answers = iter(
        [
            "y",  # enable gemini
            str(tmp_path / ".gemini"),  # gemini home path
            "n",  # enable codex (not detected, default=False)
            "n",  # enable copilot (not detected, default=False)
            "n",  # enable claude (not detected, default=False)
            "127.0.0.1",  # web host
            "8787",  # web port
            "5",  # sync interval
            "y",  # confirm
        ]
    )
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))

    cfg = AppConfig()
    out = configure_interactively(cfg, tmp_path)
    assert out.gemini.enabled is True
    assert out.codex.enabled is False
    assert out.copilot.enabled is False
    assert out.claude.enabled is False


def test_interactive_decline_reruns_flow(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Declining the final confirm triggers a second pass."""
    monkeypatch.setenv("NO_COLOR", "1")
    (tmp_path / ".gemini").mkdir()

    # First pass: decline
    # Second pass: accept
    answers = iter(
        [
            # first pass
            "y",  # enable gemini
            str(tmp_path / ".gemini"),  # gemini home path
            "n",  # codex
            "n",  # copilot
            "n",  # claude
            "127.0.0.1",  # web host
            "8787",  # web port
            "5",  # sync interval
            "n",  # DECLINE → re-run
            # second pass
            "y",  # enable gemini
            str(tmp_path / ".gemini"),  # gemini home path
            "n",  # codex
            "n",  # copilot
            "n",  # claude
            "127.0.0.1",  # web host
            "9999",  # web port (changed)
            "5",  # sync interval
            "y",  # confirm
        ]
    )
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))

    cfg = AppConfig()
    out = configure_interactively(cfg, tmp_path)
    assert out.daemon.web_port == 9999


def test_render_install_script_contains_oneliner_flow() -> None:
    script = render_install_script()
    assert "pip install --user quota-tracker" in script
    assert "quota-tracker install --interactive </dev/tty" in script
    assert "quota-tracker install\n" in script
