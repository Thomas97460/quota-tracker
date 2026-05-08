"""CLI entry point for the quota-tracker command."""

import argparse
import sys


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
    
    print(f"Command '{args.command}' is not yet implemented.")
    sys.exit(0)
