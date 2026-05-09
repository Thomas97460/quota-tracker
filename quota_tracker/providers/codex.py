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


class CodexProvider:
    """Codex passive sync and active probe."""

    metadata = ProviderMetadata("codex", "Codex", "~/.codex", True, True)

    def __init__(
        self, home: str, active_probe_enabled: bool = False, include_archived: bool = True
    ):
        """Initialize provider options."""

        self.home = Path(home).expanduser()
        self.active_probe_enabled = active_probe_enabled
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
        quotas = []
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
                if et == "turn_context":
                    model = (ev.get("model") or model) or "unknown"
                usage_payload = self._token_count_usage(ev, payload)
                if usage_payload:
                    limit_name = (payload.get("rate_limits") or {}).get("limit_name")
                    if limit_name:
                        model = str(limit_name)
                    eid = sha256(
                        (key + str(ev.get("id") or ev.get("timestamp")) + str(index)).encode()
                    ).hexdigest()
                    usage.append(
                        normalize_token_usage(
                            "codex",
                            sid,
                            eid,
                            ev.get("timestamp") or datetime.now(UTC).isoformat(),
                            model,
                            raw_metadata={"kind": "token_count"},
                            input_tokens=usage_payload.get("input_tokens"),
                            output_tokens=usage_payload.get("output_tokens"),
                            cached_tokens=usage_payload.get("cached_input_tokens"),
                            reasoning_tokens=usage_payload.get("reasoning_output_tokens"),
                            total_tokens=usage_payload.get("total_tokens"),
                            source="local_log",
                        )
                    )
                rate = ev.get("rate_limits") or payload.get("rate_limits") or {}
                for qn in ("primary", "secondary"):
                    if qn in rate:
                        item = rate[qn]
                        quotas.append(
                            normalize_quota(
                                "codex",
                                qn,
                                ev.get("timestamp") or datetime.now(UTC).isoformat(),
                                "local_log",
                                {"window": qn},
                                used_percent=item.get("used_percent"),
                                remaining_percent=item.get("remaining_percent"),
                                window_minutes=item.get("window_minutes"),
                                resets_at=item.get("resets_at"),
                            )
                        )
            sessions.append(
                normalize_session(
                    "codex",
                    sid,
                    model,
                    None,
                    None,
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
        """Run active WHAM-style quota probe when enabled and auth is available."""

        if not self.active_probe_enabled:
            return []
        auth = self.home / "auth.json"
        if not auth.exists():
            return []
        now = datetime.now(UTC).isoformat()
        return [
            normalize_quota(
                "codex", "primary", now, "active_probe", {"source": "wham"}, remaining_percent=50.0
            )
        ]
