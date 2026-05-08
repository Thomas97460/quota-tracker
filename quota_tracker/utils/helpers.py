"""Helper utilities for quota_tracker."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def parse_iso(value: str | None) -> datetime | None:
    """Parse ISO 8601 string to datetime."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def load_json(path: Path) -> Any:
    """Load JSON from path safely."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None


def mask_value(value: str | None, keep: int = 4) -> str | None:
    """Mask a sensitive value."""
    if not value:
        return value
    if len(value) <= keep:
        return "*" * len(value)
    return value[:keep] + "*" * (len(value) - keep)
