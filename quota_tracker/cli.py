"""CLI entry point for the quota-tracker command."""

import argparse
import sys


def init_db() -> None:
    """Initialize the database and apply migrations."""
    from quota_tracker.core.config import AppConfig
    from quota_tracker.database import Database, apply_migrations
    from quota_tracker.database.repositories import ProviderRepository

    config = AppConfig.load()
    db = Database(config.global_settings.database_path)
    conn = db.connect()
    try:
        apply_migrations(conn)
    finally:
        conn.close()

    # Initialize default providers
    repo = ProviderRepository(db)
    repo.initialize_default_providers()


def main() -> None:
    """Main CLI function."""
    parser = argparse.ArgumentParser(prog="quota-tracker")
    parser.add_argument("--version", action="version", version="%(prog)s 0.1.0")

    # Subparsers for commands
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Subcommands
    subparsers.add_parser("daemon", help="Start the daemon (API + scheduler)")
    subparsers.add_parser("serve", help="Start the API server and serve the frontend")
    subparsers.add_parser("scan", help="Run a one-off passive sync/scan")
    subparsers.add_parser("probe", help="Run a one-off active quota probe")
    subparsers.add_parser("migrate", help="Run database migrations")
    subparsers.add_parser(
        "install-user-service", help="Install the systemd user service"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    # Automatically apply migrations for operational commands
    if args.command in ["daemon", "serve", "scan", "probe", "migrate"]:
        init_db()
        if args.command == "migrate":
            print("Migrations applied successfully.")
            sys.exit(0)

    print(f"Command '{args.command}' is not yet implemented.")
    sys.exit(0)
