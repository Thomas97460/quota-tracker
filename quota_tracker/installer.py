"""Installer and systemd user service helpers."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from quota_tracker import _ui as ui
from quota_tracker.config import AppConfig, save_config
from quota_tracker.paths import DEFAULT_CONFIG_DIR, DEFAULT_LOG_DIR


def detect_provider_homes(home: Path) -> dict[str, str]:
    """Detect available provider home directories under the user home."""

    candidates = {
        "gemini": home / ".gemini",
        "codex": home / ".codex",
        "copilot": home / ".copilot",
        "claude": home / ".claude",
    }
    return {provider: str(path) for provider, path in candidates.items() if path.exists()}


def _input_with_default(prompt: str, default: str) -> str:
    """Read user input with fallback default value (thin wrapper over ui.prompt)."""

    return ui.prompt(prompt, default=default)


def _parse_bool(prompt: str, default: bool) -> bool:
    """Read boolean prompt with y/n values (thin wrapper over ui.confirm)."""

    return ui.confirm(prompt, default=default)


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

    for provider in ("gemini", "codex", "copilot", "claude"):
        provider_updates = updates.get(provider)
        if not isinstance(provider_updates, dict):
            continue
        target = getattr(base, provider)
        if "enabled" in provider_updates:
            target.enabled = bool(provider_updates["enabled"])
        if "home_path" in provider_updates:
            target.home_path = str(provider_updates["home_path"])
    return base


def _run_interactive_flow(config: AppConfig, home: Path) -> AppConfig:
    """Execute one pass of the interactive configuration prompts."""

    detected = detect_provider_homes(home)

    # ── Step 1/3: Detect providers ──────────────────────────────────────────
    ui.step(1, 3, "Detect providers")
    for provider in ("gemini", "codex", "copilot", "claude"):
        provider_cfg = getattr(config, provider)
        if provider in detected:
            ui.success_check(f"{provider:<8}  {detected[provider]:<20}  found")
        else:
            ui.error_mark(f"{provider:<8}  {provider_cfg.home_path:<20}  not found")

    # ── Step 2/3: Configure providers ───────────────────────────────────────
    ui.step(2, 3, "Configure providers")
    for provider in ("gemini", "codex", "copilot", "claude"):
        provider_cfg = getattr(config, provider)
        detected_home = detected.get(provider)
        default_enabled = detected_home is not None

        print(f"\n  {ui.violet('→')} {ui.bold(provider)}" if ui._is_tty() else f"\n  → {provider}")

        enabled = _parse_bool(f"Enable {provider}", default_enabled)
        provider_cfg.enabled = enabled

        if enabled:
            home_default = detected_home or provider_cfg.home_path
            provider_cfg.home_path = _input_with_default("Home path", home_default)

    # ── Step 3/3: Daemon settings ────────────────────────────────────────────
    ui.step(3, 3, "Daemon settings")
    config.daemon.web_host = _input_with_default("Web host", config.daemon.web_host)
    config.daemon.web_port = int(_input_with_default("Web port", str(config.daemon.web_port)))
    config.daemon.sync_interval_minutes = int(
        _input_with_default("Sync interval (min)", str(config.daemon.sync_interval_minutes))
    )

    # ── Summary box ──────────────────────────────────────────────────────────
    print()
    summary_lines = []
    for provider in ("gemini", "codex", "copilot", "claude"):
        pcfg = getattr(config, provider)
        state = "enabled" if pcfg.enabled else "disabled"
        summary_lines.append(f"{provider:<8}  {state:<8}  {pcfg.home_path}")
    summary_lines.append("")
    summary_lines.append(f"host     {config.daemon.web_host}:{config.daemon.web_port}")
    summary_lines.append(f"sync     every {config.daemon.sync_interval_minutes} min")
    ui.box(summary_lines, title="Configuration summary")

    return config


def configure_interactively(config: AppConfig, home: Path) -> AppConfig:
    """Prompt user for interactive installer configuration (with summary + confirmation)."""

    ui.banner()
    config = _run_interactive_flow(config, home)

    print()
    ok = ui.confirm("Continue with this config?", default=True)
    if not ok:
        print()
        ui.warn_mark("Re-running configuration from the top …")
        config = _run_interactive_flow(config, home)
        print()
        ui.confirm("Continue with this config?", default=True)

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
        "if [ -r /dev/tty ]; then\n"
        "  quota-tracker install --interactive </dev/tty\n"
        "else\n"
        "  quota-tracker install\n"
        "fi\n"
    )
