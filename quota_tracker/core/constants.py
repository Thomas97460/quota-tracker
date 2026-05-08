"""
Central constants for the quota-tracker application.
"""

from pathlib import Path

# Application Directories
APP_NAME = "quota-tracker"

DEFAULT_CONFIG_DIR = Path.home() / ".config" / APP_NAME
DEFAULT_DATA_DIR = Path.home() / ".local" / "share" / APP_NAME
DEFAULT_STATE_DIR = Path.home() / ".local" / "state" / APP_NAME

# Specific Paths
DEFAULT_DB_PATH = DEFAULT_DATA_DIR / "quota-tracker.sqlite3"
DEFAULT_LOG_DIR = DEFAULT_STATE_DIR / "logs"

# Network Settings
DEFAULT_WEB_HOST = "127.0.0.1"
DEFAULT_WEB_PORT = 8787
