"""Application default paths and network settings."""

from pathlib import Path

APP_NAME = "quota-tracker"
DEFAULT_CONFIG_DIR = Path.home() / ".config" / APP_NAME
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "config.json"
DEFAULT_DB_PATH = Path.home() / ".local" / "share" / APP_NAME / "quota-tracker.sqlite3"
DEFAULT_LOG_DIR = Path.home() / ".local" / "state" / APP_NAME / "logs"
DEFAULT_WEB_HOST = "127.0.0.1"
DEFAULT_WEB_PORT = 8787
