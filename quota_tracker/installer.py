"""Installer and systemd user service helpers."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from quota_tracker.config import AppConfig, save_config
from quota_tracker.paths import DEFAULT_CONFIG_DIR, DEFAULT_LOG_DIR


def detect_provider_homes(home: Path) -> dict[str, str]:
    """Detect available provider home directories under the user home."""

    candidates = {
        "gemini": home / ".gemini",
        "codex": home / ".codex",
        "copilot": home / ".copilot",
    }
    return {provider: str(path) for provider, path in candidates.items() if path.exists()}


def _input_with_default(prompt: str, default: str) -> str:
    """Read user input with fallback default value."""

    raw = input(f"{prompt} [{default}]: ").strip()
    return raw if raw else default


def _parse_bool(prompt: str, default: bool) -> bool:
    """Read boolean prompt with y/n values."""

    default_text = "y" if default else "n"
    value = input(f"{prompt} [y/n, default={default_text}]: ").strip().lower()
    if value not in {"", "y", "n"}:
        return default
    if value == "":
        return default
    return value == "y"


def merge_config(base: AppConfig, updates: dict[str, object]) -> AppConfig:
    """Merge known installer fields into an existing config instance."""

    for key in ("active_probe_interval_minutes", "passive_sync_interval_minutes"):
        if key in updates:
            value = updates[key]
            if not isinstance(value, int):
                raise ValueError(f"{key} must be int")
            setattr(base.daemon, key, value)
    if "web_host" in updates:
        base.daemon.web_host = str(updates["web_host"])
    if "web_port" in updates:
        web_port = updates["web_port"]
        if not isinstance(web_port, int):
            raise ValueError("web_port must be int")
        base.daemon.web_port = web_port

    for provider in ("gemini", "codex", "copilot"):
        provider_updates = updates.get(provider)
        if not isinstance(provider_updates, dict):
            continue
        target = getattr(base, provider)
        if "enabled" in provider_updates:
            target.enabled = bool(provider_updates["enabled"])
        if "home_path" in provider_updates:
            target.home_path = str(provider_updates["home_path"])
    return base


def configure_interactively(config: AppConfig, home: Path) -> AppConfig:
    """Prompt user for interactive installer configuration."""

    detected = detect_provider_homes(home)
    enable_all = _parse_bool("Enable all detected providers", True)
    for provider in ("gemini", "codex", "copilot"):
        provider_cfg = getattr(config, provider)
        detected_home = detected.get(provider, provider_cfg.home_path)
        provider_cfg.home_path = _input_with_default(f"{provider} home path", detected_home)
        default_enabled = enable_all and provider in detected
        provider_cfg.enabled = _parse_bool(f"Enable {provider}", default_enabled)

    config.daemon.web_host = _input_with_default("Web host", config.daemon.web_host)
    config.daemon.web_port = int(_input_with_default("Web port", str(config.daemon.web_port)))
    config.daemon.active_probe_interval_minutes = int(
        _input_with_default(
            "Active probe interval minutes", str(config.daemon.active_probe_interval_minutes)
        )
    )
    config.daemon.passive_sync_interval_minutes = int(
        _input_with_default(
            "Passive sync interval minutes", str(config.daemon.passive_sync_interval_minutes)
        )
    )
    return config


def ensure_directories(config: AppConfig) -> None:
    """Create required config, data, and log directories if missing."""

    DEFAULT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    Path(config.daemon.database_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_LOG_DIR.mkdir(parents=True, exist_ok=True)


def build_systemd_unit(exec_path: str, log_dir: Path) -> str:
    """Build deterministic user service content."""

    return (
        "[Unit]\n"
        "Description=quota-tracker daemon\n"
        "After=network.target\n\n"
        "[Service]\n"
        "Type=simple\n"
        f"ExecStart={exec_path} daemon\n"
        "Restart=on-failure\n"
        f"Environment=QUOTA_TRACKER_LOG_DIR={log_dir}\n"
        "StandardOutput=journal\n"
        "StandardError=journal\n\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )


def write_systemd_user_service(unit_text: str, home: Path) -> tuple[Path, bool]:
    """Write service file only when content changed."""

    unit_dir = home / ".config" / "systemd" / "user"
    unit_dir.mkdir(parents=True, exist_ok=True)
    unit_path = unit_dir / "quota-tracker.service"
    previous = unit_path.read_text() if unit_path.exists() else None
    changed = previous != unit_text
    if changed:
        unit_path.write_text(unit_text)
    return unit_path, changed


def maybe_enable_service(confirm: bool) -> None:
    """Enable and restart user service on explicit confirmation."""

    if not confirm:
        return
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
    subprocess.run(["systemctl", "--user", "enable", "quota-tracker.service"], check=False)
    subprocess.run(["systemctl", "--user", "restart", "quota-tracker.service"], check=False)


def run_install(
    config: AppConfig,
    *,
    home: Path,
    interactive: bool,
    enable_service: bool,
    exec_path: str | None = None,
) -> dict[str, object]:
    """Run installer flow and return summary."""

    if interactive:
        config = configure_interactively(config, home)
    ensure_directories(config)
    save_config(config)
    resolved_exec = exec_path or shutil.which("quota-tracker") or "quota-tracker"
    unit_text = build_systemd_unit(resolved_exec, DEFAULT_LOG_DIR)
    unit_path, changed = write_systemd_user_service(unit_text, home)
    maybe_enable_service(enable_service)
    return {
        "config": config.daemon.model_dump(),
        "service_path": str(unit_path),
        "service_updated": changed,
    }


def render_install_script() -> str:
    """Return one-liner install script body for curl|sh usage."""

    return (
        "set -eu\n"
        "TARGET=${HOME}/.local/bin\n"
        'mkdir -p "$TARGET"\n'
        "python -m pip install --user quota-tracker\n"
        "quota-tracker install --interactive\n"
    )
