"""Codex provider implementation."""

from __future__ import annotations

import json
import sqlite3
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

_WHAM_URL = "https://chatgpt.com/backend-api/wham/usage"
_WHAM_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _epoch_to_iso(value: Any) -> str | None:
    """Convert a Unix epoch integer (seconds) to an ISO 8601 string, or return None."""
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=UTC).isoformat()
    except TypeError, ValueError, OSError:
        return None


class CodexProvider:
    """Codex passive sync and active probe."""

    metadata = ProviderMetadata("codex", "Codex", "~/.codex", True, True)

    def __init__(self, home: str, include_archived: bool = True):
        """Initialize provider options."""

        self.home = Path(home).expanduser()
        self.include_archived = include_archived

    def _session_files(self) -> list[Path]:
        """Discover session files including archived files when enabled."""

        files = list(self.home.glob("sessions/**/*.jsonl"))
        if self.include_archived:
            files += list(self.home.glob("archived_sessions/*.jsonl"))
        return sorted(files)

    def _scan(self, hwm: dict[str, Any] | None = None) -> PassiveSyncResult:
        """Run full or incremental passive scan for Codex local data."""

        hwm = hwm or {}
        sessions = []
        usage: list[dict[str, Any]] = []
        quotas: list[QuotaRecord] = []
        marks = {}
        failures = 0
        for p in self._session_files():
            st = p.stat()
            key = str(p)
            prev = hwm.get(key)
            mark = {"path": key, "size": st.st_size, "mtime": st.st_mtime, "last_event_ts": None}
            if prev and prev.get("size") == st.st_size and prev.get("mtime") == st.st_mtime:
                marks[key] = mark
                continue
            sid = p.stem
            cli_version = None
            model = "unknown"
            cwd = None
            last_ts = None
            for index, line in enumerate(p.read_text(errors="replace").splitlines()):
                if not line.strip():
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    failures += 1
                    continue
                payload = self._payload(ev)
                et = ev.get("type")
                last_ts = ev.get("timestamp") or last_ts
                if et == "session_meta":
                    cli_version = (ev.get("cli") or {}).get("version")
                    cwd = payload.get("cwd") or cwd
                if et == "turn_context":
                    model = (payload.get("model") or model) or "unknown"
                usage_payload = self._token_count_usage(ev, payload)
                if usage_payload:
                    eid = sha256(
                        (key + str(ev.get("id") or ev.get("timestamp")) + str(index)).encode()
                    ).hexdigest()
                    input_t = usage_payload.get("input_tokens") or 0
                    cached_t = usage_payload.get("cached_input_tokens") or 0
                    input_t = max(0, input_t - cached_t)

                    usage.append(
                        normalize_token_usage(
                            "codex",
                            sid,
                            eid,
                            ev.get("timestamp") or datetime.now(UTC).isoformat(),
                            model,
                            raw_metadata={"kind": "token_count"},
                            input_tokens=input_t,
                            output_tokens=usage_payload.get("output_tokens"),
                            cached_tokens=cached_t,
                            reasoning_tokens=usage_payload.get("reasoning_output_tokens"),
                            total_tokens=usage_payload.get("total_tokens"),
                            source="local_log",
                        )
                    )
                # Quota tracking is exclusively handled by active probes for Codex.
            project_name = Path(cwd).name if cwd else None
            sessions.append(
                normalize_session(
                    "codex",
                    sid,
                    model,
                    cwd,
                    project_name,
                    last_ts,
                    last_ts,
                    {"cli_version": cli_version, "source_file": key},
                )
            )
            mark["last_event_ts"] = last_ts
            marks[key] = mark

        for db_name in ("state_5.sqlite", "logs_2.sqlite"):
            db_path = self.home / db_name
            if db_path.exists():
                uri = f"file:{db_path}?mode=ro"
                conn = sqlite3.connect(uri, uri=True)
                conn.close()

        return PassiveSyncResult(sessions, usage, quotas, marks, failures)

    @staticmethod
    def _payload(event: dict[str, Any]) -> dict[str, Any]:
        """Return nested Codex event payload when present."""

        value = event.get("payload")
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _token_count_usage(event: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        """Extract per-event Codex token usage from legacy and current log shapes."""

        direct = event.get("usage")
        if event.get("type") == "token_count" and isinstance(direct, dict):
            return direct
        info = payload.get("info")
        if payload.get("type") == "token_count" and isinstance(info, dict):
            for key in ("last_token_usage", "usage", "total_token_usage"):
                value = info.get(key)
                if isinstance(value, dict):
                    return value
        return {}

    def passive_scan_full(self) -> PassiveSyncResult:
        """Run full passive scan."""

        return self._scan({})

    def passive_scan_incremental(self, high_water_marks: dict[str, Any]) -> PassiveSyncResult:
        """Run incremental passive scan."""

        return self._scan(high_water_marks)

    def active_probe(self) -> list[QuotaRecord]:
        """Probe the WHAM endpoint for live Codex rate-limit data."""

        auth_path = self.home / "auth.json"
        if not auth_path.exists():
            return []
        try:
            auth = json.loads(auth_path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            return []
        access_token = (auth.get("tokens") or {}).get("access_token") or ""
        if not isinstance(access_token, str) or not access_token:
            return []
        try:
            data = get_json(
                _WHAM_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "User-Agent": _WHAM_USER_AGENT,
                    "Accept": "*/*",
                },
            )
        except Exception:
            return []
        rate_limit = data.get("rate_limit")
        if not isinstance(rate_limit, dict):
            return []
        now = datetime.now(UTC).isoformat()
        records: list[QuotaRecord] = []
        for window_name in ("primary", "secondary"):
            window = rate_limit.get(f"{window_name}_window")
            if not isinstance(window, dict):
                continue
            used_pct = window.get("used_percent")
            limit_secs = window.get("limit_window_seconds")
            reset_at = window.get("reset_at")
            records.append(
                normalize_quota(
                    "codex",
                    window_name,
                    now,
                    "active_probe",
                    {"window": window_name, "limit_window_seconds": limit_secs},
                    used_percent=float(used_pct) if used_pct is not None else None,
                    remaining_percent=(
                        round(100.0 - float(used_pct), 4) if used_pct is not None else None
                    ),
                    window_minutes=int(limit_secs) // 60 if limit_secs is not None else None,
                    resets_at=_epoch_to_iso(reset_at),
                )
            )
        return records
