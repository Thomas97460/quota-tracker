"""CLI entrypoint for quota-tracker."""

from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from quota_tracker import __version__
from quota_tracker.api import create_app
from quota_tracker.config import (
    AppConfig,
    config_file_path,
    default_config_json,
    load_config,
    sanitized_config_json,
    save_config,
)
from quota_tracker.daemon import DaemonService
from quota_tracker.db import apply_migrations, connect_db
from quota_tracker.installer import (
    render_install_script,
    run_install,
    sync_provider_rows_from_config,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""

    parser = argparse.ArgumentParser(prog="quota-tracker")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("show-default-config")
    sub.add_parser("config-path")
    sub.add_parser("migrate")

    config_parser = sub.add_parser("config")
    config_sub = config_parser.add_subparsers(dest="config_command")
    config_sub.add_parser("show")
    config_set = config_sub.add_parser("set")
    config_set.add_argument("--provider", choices=["gemini", "codex", "copilot", "claude"])
    config_set.add_argument("--enabled", choices=["true", "false"])
    config_set.add_argument("--home-path")
    config_set.add_argument("--active-probe-enabled", choices=["true", "false"])
    config_set.add_argument("--passive-sync-enabled", choices=["true", "false"])
    config_set.add_argument("--active-probe-interval-minutes", type=int)
    config_set.add_argument("--passive-sync-interval-minutes", type=int)
    config_set.add_argument("--host")
    config_set.add_argument("--port", type=int)
    config_set.add_argument("--database-path")
    config_set.add_argument("--log-level")

    scan = sub.add_parser("scan")
    scan.add_argument(
        "--provider", choices=["all", "gemini", "codex", "copilot", "claude"], default="all"
    )
    scan.add_argument("--full", action="store_true")
    probe = sub.add_parser("probe")
    probe.add_argument(
        "--provider", choices=["all", "gemini", "codex", "copilot", "claude"], default="all"
    )
    probe.add_argument("--dry-run", action="store_true")
    sub.add_parser("daemon")
    sub.add_parser("serve")
    install = sub.add_parser("install")
    install.add_argument("--interactive", action="store_true")
    install.add_argument("--enable-service", action="store_true")
    install.add_argument("--exec-path")
    install_service = sub.add_parser("install-user-service")
    install_service.add_argument("--exec-path")
    sub.add_parser("install-script")

    return parser


def _parse_bool(value: str | None) -> bool | None:
    """Parse true/false flags encoded as strings."""

    if value is None:
        return None
    return value == "true"


def _validate_interval(value: int | None, field_name: str) -> None:
    """Validate interval minute values."""

    if value is None:
        return
    if value <= 0:
        raise ValueError(f"{field_name} must be > 0")


def _validate_port(port: int | None) -> None:
    """Validate TCP port."""

    if port is None:
        return
    if port < 1 or port > 65535:
        raise ValueError("port must be in [1, 65535]")


def _apply_config_set(config: AppConfig, args: argparse.Namespace) -> AppConfig:
    """Apply config set mutations and validate values."""

    _validate_interval(args.active_probe_interval_minutes, "active_probe_interval_minutes")
    _validate_interval(args.passive_sync_interval_minutes, "passive_sync_interval_minutes")
    _validate_port(args.port)
    if args.home_path:
        Path(args.home_path).expanduser()
    if args.database_path:
        Path(args.database_path).expanduser()

    if args.active_probe_interval_minutes is not None:
        config.daemon.active_probe_interval_minutes = args.active_probe_interval_minutes
    if args.passive_sync_interval_minutes is not None:
        config.daemon.passive_sync_interval_minutes = args.passive_sync_interval_minutes
    if args.host is not None:
        config.daemon.web_host = args.host
    if args.port is not None:
        config.daemon.web_port = args.port
    if args.database_path is not None:
        config.daemon.database_path = str(Path(args.database_path).expanduser())
    if args.log_level is not None:
        config.daemon.log_level = args.log_level

    if args.provider:
        provider_cfg = getattr(config, args.provider)
        provider_cfg.active_probe_enabled = True
        enabled = _parse_bool(args.enabled)
        if enabled is not None:
            provider_cfg.enabled = enabled
        if args.home_path is not None:
            provider_cfg.home_path = str(Path(args.home_path).expanduser())
        active_probe = _parse_bool(args.active_probe_enabled)
        if active_probe is not None:
            provider_cfg.active_probe_enabled = True
        passive_sync = _parse_bool(args.passive_sync_enabled)
        if passive_sync is not None:
            provider_cfg.passive_sync_enabled = passive_sync
    return config


def _service_from_config(config: AppConfig) -> DaemonService:
    """Instantiate daemon service from config."""

    return DaemonService(
        db_path=config.daemon.database_path,
        sync_interval_minutes=config.daemon.sync_interval_minutes,
        passive_sync_interval_minutes=config.daemon.passive_sync_interval_minutes,
        active_probe_interval_minutes=config.daemon.active_probe_interval_minutes,
        log_level=config.daemon.log_level,
    )


def main() -> int:
    """Run the quota-tracker command."""

    parser = build_parser()
    try:
        args = parser.parse_args()
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 2

    if args.command is None:
        print(default_config_json())
        return 0
    if args.command == "show-default-config":
        print(default_config_json())
        return 0
    if args.command == "config-path":
        print(config_file_path())
        return 0
    if args.command == "config":
        config = load_config()
        if args.config_command == "show":
            print(sanitized_config_json(config))
            return 0
        if args.config_command == "set":
            try:
                updated = _apply_config_set(config, args)
            except ValueError as exc:
                print(str(exc))
                return 2
            save_config(updated)
            sync_provider_rows_from_config(updated)
            print(sanitized_config_json(updated))
            return 0
        print("unknown config subcommand")
        return 2
    if args.command == "migrate":
        config = load_config()
        conn = connect_db(config.daemon.database_path)
        try:
            newly_applied = apply_migrations(conn)
            row = conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()
            total = row[0] if row else 0
        finally:
            conn.close()
        sync_provider_rows_from_config(config)
        if newly_applied:
            ids = ", ".join(newly_applied)
            print(f"applied {len(newly_applied)} new migration(s): {ids}")
        else:
            print(f"up-to-date ({total} migrations applied)")
        return 0
    if args.command == "scan":
        config = load_config()
        service = _service_from_config(config)
        service.migrate_and_prepare()
        summary = service.run_scan(provider=args.provider, full=args.full)
        print(
            f"sessions_upserted={summary.sessions_upserted} "
            f"token_rows_inserted={summary.token_rows_inserted} "
            f"quota_rows_inserted={summary.quota_rows_inserted} "
            f"parse_failures={summary.parse_failures}"
        )
        return 0
    if args.command == "probe":
        config = load_config()
        service = _service_from_config(config)
        service.migrate_and_prepare()
        if args.dry_run:
            print("dry-run: no live probe executed")
            return 0
        summary = service.run_probe(provider=args.provider)
        print(f"quota_rows_inserted={summary.quota_rows_inserted}")
        return 0
    if args.command == "serve":
        config = load_config()
        app = create_app(db_path=Path(config.daemon.database_path))
        uvicorn.run(app, host=config.daemon.web_host, port=config.daemon.web_port)
        return 0
    if args.command == "daemon":
        config = load_config()
        service = _service_from_config(config)
        service.migrate_and_prepare()
        service.start_scheduler()
        app = create_app(service=service, db_path=Path(config.daemon.database_path))
        try:
            uvicorn.run(app, host=config.daemon.web_host, port=config.daemon.web_port)
        finally:
            service.stop_scheduler()
        return 0
    if args.command == "install":
        config = load_config()
        install_summary = run_install(
            config,
            home=Path.home(),
            interactive=args.interactive,
            enable_service=args.enable_service,
            exec_path=args.exec_path,
        )
        cfg_path = config_file_path()
        svc_path = install_summary["service_path"]
        status_str = "updated" if install_summary["service_updated"] else "unchanged"
        print(f"config: {cfg_path}")
        print(f"service: {svc_path} ({status_str})")
        return 0
    if args.command == "install-user-service":
        config = load_config()
        install_summary = run_install(
            config,
            home=Path.home(),
            interactive=False,
            enable_service=True,
            exec_path=args.exec_path,
        )
        svc_path = install_summary["service_path"]
        status_str = "updated" if install_summary["service_updated"] else "unchanged"
        print(f"service: {svc_path} ({status_str})")
        return 0
    if args.command == "install-script":
        print(render_install_script())
        return 0

    print(f"unknown command: {args.command}")  # pragma: no cover
    return 2  # pragma: no cover


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
