"""CLI entry point for the quota-tracker command."""

import argparse
import sys


def main() -> None:
    """Main CLI function."""
    parser = argparse.ArgumentParser(prog="quota-tracker")
    parser.add_argument("--version", action="version", version="%(prog)s 0.1.0")
    
    # Subparsers for commands
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Dummy commands for now to satisfy requirements
    subparsers.add_parser("daemon", help="Start the daemon")
    subparsers.add_parser("scan", help="Run a one-off scan")
    subparsers.add_parser("probe", help="Run a one-off quota probe")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(0)
    
    print(f"Command '{args.command}' is not yet implemented.")
    sys.exit(0)
