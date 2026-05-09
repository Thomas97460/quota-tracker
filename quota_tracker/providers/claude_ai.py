"""Claude.ai provider — active quota probe via the usage API."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tempfile
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from quota_tracker.db import QuotaRecord
from quota_tracker.providers.base import (
    PassiveSyncResult,
    ProviderMetadata,
    normalize_quota,
    normalize_session,
    normalize_token_usage,
)
from quota_tracker.providers.http import get_json

_CLAUDE_USAGE_URL = "https://claude.ai/api/organizations/{org_id}/usage"
_CLAUDE_ORGS_URL = "https://claude.ai/api/organizations"
_CLAUDE_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_CREDENTIALS_FILE = "quota_tracker_creds.json"

_BUCKET_DISPLAY: dict[str, str] = {
    "five_hour": "5h",
    "seven_day": "weekly",
}
_BUCKET_WINDOW_MINUTES: dict[str, int] = {
    "five_hour": 300,
    "seven_day": 10080,
}

_CLAUDE_REQUEST_HEADERS = {
    "Accept": "application/json",
    "User-Agent": _CLAUDE_USER_AGENT,
    "anthropic-client-platform": "web_claude_ai",
    "anthropic-client-version": "1.0.0",
}


def _as_int(value: Any) -> int:
    """Return a non-negative integer token count, defaulting invalid values to 0."""

    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _project_path_from_slug(slug: str) -> str | None:
    """Best-effort decode Claude Code project directory names like -home-user-repo."""

    if not slug.startswith("-"):
        return None
    return "/" + slug.lstrip("-").replace("-", "/")


def _safe_usage_metadata(usage: dict[str, Any]) -> dict[str, Any]:
    """Keep numeric Claude usage metadata while excluding message content."""

    metadata: dict[str, Any] = {
        "input_tokens": _as_int(usage.get("input_tokens")),
        "output_tokens": _as_int(usage.get("output_tokens")),
        "cache_creation_input_tokens": _as_int(usage.get("cache_creation_input_tokens")),
        "cache_read_input_tokens": _as_int(usage.get("cache_read_input_tokens")),
    }
    service_tier = usage.get("service_tier")
    if isinstance(service_tier, str):
        metadata["service_tier"] = service_tier
    speed = usage.get("speed")
    if isinstance(speed, str):
        metadata["speed"] = speed
    server_tool_use = usage.get("server_tool_use")
    if isinstance(server_tool_use, dict):
        metadata["server_tool_use"] = {
            key: _as_int(value) for key, value in server_tool_use.items() if isinstance(key, str)
        }
    cache_creation = usage.get("cache_creation")
    if isinstance(cache_creation, dict):
        metadata["cache_creation"] = {
            key: _as_int(value) for key, value in cache_creation.items() if isinstance(key, str)
        }
    return metadata


def _load_session_key_from_file(home: Path) -> str | None:
    """Load session_key from quota_tracker_creds.json (only session_key is required)."""
    creds_path = home / _CREDENTIALS_FILE
    if not creds_path.exists():
        return None
    try:
        data = json.loads(creds_path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    session_key = data.get("session_key")
    if not isinstance(session_key, str) or not session_key.strip():
        return None
    return session_key.strip()


def _load_session_key_from_firefox() -> str | None:
    """Try to read claude.ai sessionKey cookie from Firefox (no decryption needed)."""
    firefox_dir = Path.home() / ".mozilla" / "firefox"
    if not firefox_dir.exists():
        return None
    cookie_dbs = sorted(
        firefox_dir.glob("*/cookies.sqlite"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for cookies_path in cookie_dbs:
        try:
            with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tmp:
                shutil.copy2(cookies_path, tmp.name)
                tmp_path = tmp.name
            try:
                conn = sqlite3.connect(tmp_path)
                cur = conn.execute(
                    "SELECT value FROM moz_cookies"
                    " WHERE host LIKE '%.claude.ai' AND name = 'sessionKey'"
                    " ORDER BY expiry DESC LIMIT 1"
                )
                row = cur.fetchone()
                conn.close()
                if row and isinstance(row[0], str) and row[0].strip():
                    return row[0].strip()
            finally:
                os.unlink(tmp_path)
        except Exception:
            continue
    return None


def _load_session_key(home: Path) -> str | None:
    """Return a session key: credentials file first, then Firefox auto-detection."""
    key = _load_session_key_from_file(home)
    if key:
        return key
    return _load_session_key_from_firefox()


def _fetch_org_id(session_key: str) -> str | None:
    """Fetch the organization UUID from /api/organizations using the session key.

    get_json wraps list responses as {"value": [...]}, so we unwrap when needed.
    """
    try:
        data = get_json(
            _CLAUDE_ORGS_URL,
            headers={
                **_CLAUDE_REQUEST_HEADERS,
                "Cookie": f"sessionKey={session_key}",
            },
        )
    except Exception:
        return None
    orgs = data.get("value") if isinstance(data, dict) else data
    if not isinstance(orgs, list) or not orgs:
        return None
    org = orgs[0]
    uuid = org.get("uuid") if isinstance(org, dict) else None
    return uuid if isinstance(uuid, str) and uuid.strip() else None


def _parse_usage_response(data: dict[str, Any], now: str) -> list[QuotaRecord]:
    """Parse the claude.ai usage API response into normalized quota records.

    Real response shape (as observed):
        {
          "five_hour":  {"utilization": 22.0, "resets_at": "2026-05-09T19:10:00+00:00"},
          "seven_day":  {"utilization": 43.0, "resets_at": "2026-05-13T05:00:00+00:00"},
          "seven_day_omelette": {"utilization": 85.0, "resets_at": "..."},
          "seven_day_opus": null,
          ...
        }
    `utilization` is already a percentage (0–100). Null buckets are skipped.
    """
    records: list[QuotaRecord] = []
    for bucket_key, value in data.items():
        if not isinstance(value, dict):
            continue
        utilization = value.get("utilization")
        if utilization is None:
            continue
        try:
            used_pct = float(utilization)
        except (TypeError, ValueError):
            continue
        resets_at = value.get("resets_at")
        if isinstance(resets_at, str) and not resets_at.strip():
            resets_at = None
        quota_name = _BUCKET_DISPLAY.get(bucket_key, bucket_key)
        window_minutes = _BUCKET_WINDOW_MINUTES.get(bucket_key)
        records.append(
            normalize_quota(
                "claude",
                quota_name,
                now,
                "active_probe",
                {"bucket": bucket_key, "utilization": used_pct},
                used_percent=used_pct,
                remaining_percent=round(100.0 - used_pct, 4),
                window_minutes=window_minutes,
                resets_at=resets_at,
            )
        )
    return records


class ClaudeAiProvider:
    """Claude.ai active quota probe and Claude Code passive usage sync.

    Credentials are loaded automatically from (in order):
      1. ~/.claude/quota_tracker_creds.json  {"session_key": "sk-ant-sid02-..."}
      2. Firefox cookies for claude.ai (no decryption needed)

    The organization UUID is discovered at runtime via /api/organizations.
    """

    metadata = ProviderMetadata("claude", "Claude", "~/.claude", True, True)

    def __init__(self, home: str):
        self.home = Path(home).expanduser()

    def _session_files(self) -> list[Path]:
        """Discover Claude Code local project transcripts."""

        return sorted((self.home / "projects").glob("*/*.jsonl"))

    def _scan(self, high_water_marks: dict[str, Any] | None = None) -> PassiveSyncResult:
        """Run full or incremental passive scan for Claude Code local data."""

        high_water_marks = high_water_marks or {}
        sessions = []
        token_usage: list[dict[str, Any]] = []
        marks: dict[str, Any] = {}
        parse_failures = 0

        for path in self._session_files():
            stat = path.stat()
            key = str(path)
            previous = high_water_marks.get(key)
            mark = {
                "path": key,
                "size": stat.st_size,
                "mtime": stat.st_mtime,
                "last_event_ts": None,
            }
            if (
                previous
                and previous.get("size") == stat.st_size
                and previous.get("mtime") == stat.st_mtime
            ):
                marks[key] = mark
                continue

            external_session_id = path.stem
            project_slug = path.parent.name
            project_path = _project_path_from_slug(project_slug)
            project_name = Path(project_path).name if project_path else project_slug
            model_name = "unknown"
            created_at = None
            last_seen_at = None
            cli_version = None
            git_branch = None
            usage_by_event: dict[str, dict[str, Any]] = {}

            for index, line in enumerate(
                path.read_text(encoding="utf-8", errors="replace").splitlines()
            ):
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    parse_failures += 1
                    continue
                if not isinstance(event, dict):
                    continue

                timestamp = event.get("timestamp")
                if isinstance(timestamp, str) and timestamp:
                    created_at = created_at or timestamp
                    last_seen_at = timestamp
                    mark["last_event_ts"] = timestamp
                session_id = event.get("sessionId")
                if isinstance(session_id, str) and session_id.strip():
                    external_session_id = session_id.strip()
                cwd = event.get("cwd")
                if isinstance(cwd, str) and cwd.strip():
                    project_path = cwd.strip()
                    project_name = Path(project_path).name
                version = event.get("version")
                if isinstance(version, str) and version.strip():
                    cli_version = version.strip()
                branch = event.get("gitBranch")
                if isinstance(branch, str) and branch.strip():
                    git_branch = branch.strip()

                message = event.get("message")
                if not isinstance(message, dict):
                    continue
                model = message.get("model")
                if isinstance(model, str) and model.strip():
                    model_name = model.strip()
                usage = message.get("usage")
                if not isinstance(usage, dict):
                    continue

                message_id = message.get("id")
                uuid = event.get("uuid")
                event_id = str(message_id or uuid or sha256(f"{key}:{index}".encode()).hexdigest())
                input_tokens = _as_int(usage.get("input_tokens"))
                output_tokens = _as_int(usage.get("output_tokens"))
                cache_creation_tokens = _as_int(usage.get("cache_creation_input_tokens"))
                cache_read_tokens = _as_int(usage.get("cache_read_input_tokens"))
                cached_tokens = cache_creation_tokens + cache_read_tokens
                total_tokens = _as_int(usage.get("total_tokens")) or (
                    input_tokens + output_tokens + cached_tokens
                )
                usage_by_event[event_id] = normalize_token_usage(
                    "claude",
                    external_session_id,
                    event_id,
                    (
                        timestamp
                        if isinstance(timestamp, str) and timestamp
                        else datetime.now(UTC).isoformat()
                    ),
                    model_name,
                    raw_metadata=_safe_usage_metadata(usage),
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cached_tokens=cached_tokens,
                    total_tokens=total_tokens,
                    source="local_log",
                )

            sessions.append(
                normalize_session(
                    "claude",
                    external_session_id,
                    model_name,
                    project_path,
                    project_name,
                    created_at,
                    last_seen_at,
                    {
                        "source_file": key,
                        "cli_version": cli_version,
                        "git_branch": git_branch,
                    },
                )
            )
            token_usage.extend(usage_by_event.values())
            marks[key] = mark

        return PassiveSyncResult(sessions, token_usage, [], marks, parse_failures)

    def passive_scan_full(self) -> PassiveSyncResult:
        return self._scan({})

    def passive_scan_incremental(self, high_water_marks: dict[str, Any]) -> PassiveSyncResult:
        return self._scan(high_water_marks)

    def active_probe(self) -> list[QuotaRecord]:
        """Fetch usage quotas from the claude.ai organization usage API."""
        session_key = _load_session_key(self.home)
        if not session_key:
            return []
        org_id = _fetch_org_id(session_key)
        if not org_id:
            return []
        url = _CLAUDE_USAGE_URL.format(org_id=org_id)
        try:
            data = get_json(
                url,
                headers={
                    **_CLAUDE_REQUEST_HEADERS,
                    "Content-Type": "application/json",
                    "Cookie": f"sessionKey={session_key}",
                },
            )
        except Exception:
            return []
        now = datetime.now(UTC).isoformat()
        return _parse_usage_response(data, now)
