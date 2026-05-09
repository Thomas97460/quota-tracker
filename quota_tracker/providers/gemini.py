"""Gemini provider implementation."""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
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
from quota_tracker.providers.http import post_json, ssl_context

_CODE_ASSIST_ENDPOINT = "https://cloudcode-pa.googleapis.com"
_CODE_ASSIST_API_VERSION = "v1internal"
_CODE_ASSIST_METADATA: dict[str, str] = {
    "ideType": "IDE_UNSPECIFIED",
    "platform": "PLATFORM_UNSPECIFIED",
    "pluginType": "GEMINI",
}
_OAUTH_CLIENT_ID = "681255809395-oo8ft2oprdrnp9e3aqf6av3hmdib135j.apps.googleusercontent.com"
_OAUTH_CLIENT_SECRET = "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"
_OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"


def _code_assist_url(method: str) -> str:
    """Build a Code Assist API endpoint URL for the given RPC method name."""
    return f"{_CODE_ASSIST_ENDPOINT.rstrip('/')}/{_CODE_ASSIST_API_VERSION}:{method}"


def _oauth_expired(creds: dict[str, Any], skew_seconds: int = 60) -> bool:
    """Return True if the OAuth access token is expired or about to expire."""
    expiry_ms = creds.get("expiry_date")
    if not expiry_ms:
        return False
    try:
        return int(expiry_ms) <= int((time.time() + skew_seconds) * 1000)
    except (TypeError, ValueError):
        return False


def _get_access_token(creds: dict[str, Any], timeout_seconds: int = 20) -> str | None:
    """Return a valid OAuth access token, refreshing via refresh_token when expired."""
    access = creds.get("access_token")
    if isinstance(access, str) and access and not _oauth_expired(creds):
        return access
    refresh = creds.get("refresh_token")
    if not isinstance(refresh, str) or not refresh:
        return access if isinstance(access, str) else None
    form = urllib.parse.urlencode(
        {
            "client_id": _OAUTH_CLIENT_ID,
            "client_secret": _OAUTH_CLIENT_SECRET,
            "refresh_token": refresh,
            "grant_type": "refresh_token",
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        _OAUTH_TOKEN_URL,
        data=form,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout_seconds, context=ssl_context()) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="replace"))
    refreshed = data.get("access_token")
    return refreshed if isinstance(refreshed, str) else None


def _retrieve_quota_buckets(
    token: str, project: str, timeout_seconds: int = 20
) -> list[dict[str, Any]]:
    """Call retrieveUserQuota and return a normalized list of quota bucket dicts."""
    result = post_json(
        _code_assist_url("retrieveUserQuota"),
        {"project": project},
        bearer_token=token,
        timeout_seconds=timeout_seconds,
    )
    raw = result.get("buckets")
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for bucket in raw:
        if not isinstance(bucket, dict):
            continue
        model_id = bucket.get("modelId")
        token_type = bucket.get("tokenType")
        if not model_id or not token_type:
            continue
        rf = bucket.get("remainingFraction")
        try:
            rf_float = float(rf) if rf is not None else None
        except (TypeError, ValueError):
            rf_float = None
        out.append(
            {
                "model_id": str(model_id),
                "token_type": str(token_type),
                "reset_time": bucket.get("resetTime"),
                "remaining_percent": round(rf_float * 100, 4) if rf_float is not None else None,
                "used_percent": (
                    round((1.0 - rf_float) * 100, 4) if rf_float is not None else None
                ),
            }
        )
    return out


class GeminiProvider:
    """Gemini passive sync and active probe."""

    metadata = ProviderMetadata("gemini", "Gemini", "~/.gemini", True, True)

    def __init__(self, home: str, active_probe_enabled: bool = False):
        """Initialize provider with home path and active probe flag."""
        self.home = Path(home).expanduser()
        self.active_probe_enabled = active_probe_enabled

    def _discover_chat_files(self) -> list[Path]:
        """Discover supported Gemini chat JSON/JSONL files."""
        return sorted(
            list(self.home.glob("**/chats/*.json")) + list(self.home.glob("**/chats/*.jsonl"))
        )

    def _parse_chat_file(self, path: Path) -> tuple[list[dict[str, Any]], int]:
        """Parse one chat file and return events plus parse failure count."""
        failures = 0
        events: list[dict[str, Any]] = []
        if path.suffix == ".jsonl":
            for line in path.read_text(errors="replace").splitlines():
                if not line.strip():
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    failures += 1
        else:
            try:
                data = json.loads(path.read_text(errors="replace"))
                if isinstance(data, list):
                    events.extend(data)
                elif isinstance(data, dict):
                    events.extend(data.get("events", []))
            except json.JSONDecodeError:
                failures += 1
        return events, failures

    def _scan(self, high_water_marks: dict[str, Any] | None = None) -> PassiveSyncResult:
        """Run full or incremental scan depending on provided high-water marks."""
        high_water_marks = high_water_marks or {}
        sessions = []
        usage: list[dict[str, Any]] = []
        failures = 0
        marks: dict[str, Any] = {}
        for path in self._discover_chat_files():
            stat = path.stat()
            key = str(path)
            prev = high_water_marks.get(key)
            file_mark = {
                "path": key,
                "size": stat.st_size,
                "mtime": stat.st_mtime,
                "last_event_ts": None,
            }
            if prev and prev.get("size") == stat.st_size and prev.get("mtime") == stat.st_mtime:
                marks[key] = file_mark
                continue
            events, f = self._parse_chat_file(path)
            failures += f
            sid = path.stem
            project_hash = None
            cli_version = None
            last_ts = None
            for ev in events:
                last_ts = ev.get("timestamp") or last_ts
                project_hash = ev.get("project_hash") or project_hash
                cli_version = ev.get("cli_version") or cli_version
                tok = ev.get("tokens") or {}
                if tok:
                    eid = sha256(
                        (key + str(ev.get("id") or ev.get("timestamp") or len(usage))).encode()
                    ).hexdigest()
                    n = normalize_token_usage(
                        provider_id="gemini",
                        external_session_id=sid,
                        external_event_id=eid,
                        timestamp=ev.get("timestamp") or datetime.now(UTC).isoformat(),
                        model_name=ev.get("model"),
                        input_tokens=tok.get("input"),
                        output_tokens=tok.get("output"),
                        cached_tokens=tok.get("cached"),
                        reasoning_tokens=tok.get("reasoning"),
                        total_tokens=tok.get("total"),
                        raw_metadata={"kind": ev.get("kind")},
                    )
                    usage.append(n)
            sessions.append(
                normalize_session(
                    provider_id="gemini",
                    external_session_id=sid,
                    model_name="unknown",
                    project_path=None,
                    project_name=None,
                    created_at=last_ts,
                    last_seen_at=last_ts,
                    metadata={
                        "project_hash": project_hash,
                        "cli_version": cli_version,
                        "source_file": key,
                    },
                )
            )
            file_mark["last_event_ts"] = last_ts
            marks[key] = file_mark
        return PassiveSyncResult(sessions, usage, [], marks, failures)

    def passive_scan_full(self) -> PassiveSyncResult:
        """Run full passive scan."""
        return self._scan({})

    def passive_scan_incremental(self, high_water_marks: dict[str, Any]) -> PassiveSyncResult:
        """Run incremental passive scan from high-water marks."""
        return self._scan(high_water_marks)

    def active_probe(self) -> list[QuotaRecord]:
        """Run active Code Assist quota probe using local OAuth credentials."""
        if not self.active_probe_enabled:
            return []
        oauth_path = self.home / "oauth_creds.json"
        if not oauth_path.exists():
            return []
        try:
            creds = json.loads(oauth_path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            return []
        if not isinstance(creds, dict):
            return []
        try:
            token = _get_access_token(creds)
            if not token:
                return []
            load_result = post_json(
                _code_assist_url("loadCodeAssist"),
                {"cloudaicompanionProject": None, "metadata": _CODE_ASSIST_METADATA},
                bearer_token=token,
            )
            project = load_result.get("cloudaicompanionProject")
            if not isinstance(project, str) or not project:
                return []
            buckets = _retrieve_quota_buckets(token, project)
        except Exception:
            return []
        now = datetime.now(UTC).isoformat()
        return [
            normalize_quota(
                provider_id="gemini",
                quota_name=f"{b['model_id']}/{b['token_type']}",
                timestamp=now,
                source="active_probe",
                raw_metadata={"model_id": b["model_id"], "token_type": b["token_type"]},
                remaining_percent=b.get("remaining_percent"),
                used_percent=b.get("used_percent"),
                resets_at=b.get("reset_time"),
            )
            for b in buckets
        ]
