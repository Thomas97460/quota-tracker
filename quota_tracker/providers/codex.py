"""Codex provider implementation."""

import hashlib
import json
import logging
import os
import sqlite3
import ssl
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from quota_tracker.core.models import QuotaRecord, SessionRecord, TokenUsageRecord
from quota_tracker.providers.base import BaseProvider
from quota_tracker.utils.helpers import load_json, parse_iso

logger = logging.getLogger(__name__)

WHAM_BACKEND_URL = "https://chatgpt.com/backend-api/wham/usage"


class CodexProvider(BaseProvider):
    """Codex provider implementation."""

    @property
    def provider_id(self) -> str:
        """Return the unique identifier for the provider."""
        return "codex"

    @property
    def display_name(self) -> str:
        """Return the human-readable name of the provider."""
        return "Codex"

    @property
    def default_home_path(self) -> str:
        """Return the default home path for the provider."""
        return "~/.codex"

    @property
    def supports_active_probe(self) -> bool:
        """Return True if the provider supports active quota probing."""
        return True

    @property
    def supports_passive_sync(self) -> bool:
        """Return True if the provider supports passive history syncing."""
        return True

    def scan_passive(
        self, home_path: str
    ) -> Iterable[SessionRecord | TokenUsageRecord | QuotaRecord]:
        """Perform a full passive scan of local history.

        Args:
            home_path: The path to the Codex home directory.

        Yields:
            SessionRecord, TokenUsageRecord, and QuotaRecord objects.
        """
        home = Path(home_path).expanduser()

        # 1. JSONL Session Files
        for path in self._iter_session_files(home):
            try:
                yield from self._parse_session_file(path)
            except Exception:
                logger.exception("Failed to parse Codex session file: %s", path)

        # 2. state_5.sqlite
        try:
            yield from self._sync_state_db(home)
        except Exception:
            logger.exception("Failed to sync Codex state_5.sqlite")

        # 3. logs_2.sqlite
        try:
            yield from self._sync_logs_db(home)
        except Exception:
            logger.exception("Failed to sync Codex logs_2.sqlite")

    def scan_incremental(
        self, home_path: str, sync_state: dict[str, Any]
    ) -> Iterable[SessionRecord | TokenUsageRecord | QuotaRecord]:
        """Perform an incremental passive scan of local history.

        Args:
            home_path: The path to the Codex home directory.
            sync_state: A dictionary containing high-water marks.

        Yields:
            SessionRecord, TokenUsageRecord, and QuotaRecord objects.
        """
        home = Path(home_path).expanduser()

        # 1. JSONL Session Files
        for path in self._iter_session_files(home):
            path_str = str(path)
            try:
                stat = path.stat()
                mtime = stat.st_mtime
                size = stat.st_size

                hwm = sync_state.get(path_str)
                if hwm and hwm.get("mtime") == mtime and hwm.get("size") == size:
                    continue

                yield from self._parse_session_file(path)

                sync_state[path_str] = {
                    "mtime": mtime,
                    "size": size,
                    "last_processed_at": datetime.now(UTC).isoformat(),
                }
            except Exception:
                logger.exception("Failed to parse Codex session file: %s", path)

        # 2. state_5.sqlite
        try:
            yield from self._sync_state_db(home, sync_state)
        except Exception:
            logger.exception("Failed to sync Codex state_5.sqlite")

        # 3. logs_2.sqlite
        try:
            yield from self._sync_logs_db(home, sync_state)
        except Exception:
            logger.exception("Failed to sync Codex logs_2.sqlite")

    def probe_active(self, home_path: str) -> Iterable[QuotaRecord]:
        """Perform an active quota probe.

        Args:
            home_path: The path to the Codex home directory.

        Yields:
            QuotaRecord objects representing current quota usage.
        """
        home = Path(home_path).expanduser()
        auth_path = home / "auth.json"
        auth_data = load_json(auth_path)
        if not isinstance(auth_data, dict):
            logger.warning("Codex auth.json not found or invalid at %s", auth_path)
            return

        access_token = auth_data.get("tokens", {}).get("access_token")
        if not access_token:
            logger.warning("Codex access token unavailable in auth.json")
            return

        try:
            wham_res = self._http_get_json(WHAM_BACKEND_URL, bearer_token=access_token)
            yield from self._parse_wham_usage(wham_res)
        except Exception:
            logger.exception("Codex active quota probe failed")

    def _iter_session_files(self, home: Path) -> list[Path]:
        """Iterate over all Codex session files."""
        files = list((home / "sessions").glob("**/*.jsonl"))
        # Archived sessions are included by default unless we add a config to disable it
        # For now, following codex_local_audit.py pattern
        files.extend((home / "archived_sessions").glob("*.jsonl"))
        return sorted(path for path in files if path.is_file())

    def _parse_session_file(
        self, path: Path
    ) -> Iterable[SessionRecord | TokenUsageRecord | QuotaRecord]:
        """Parse a single JSONL session file."""
        session_id = None
        cwd = None
        model = None
        cli_version = None
        started_at: datetime | None = None
        first_event_ts: datetime | None = None
        last_event_ts: datetime | None = None

        token_records: list[TokenUsageRecord] = []
        quota_records: list[QuotaRecord] = []

        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue

                record_type = record.get("type")
                payload = record.get("payload") or {}
                timestamp_str = record.get("timestamp")
                timestamp = parse_iso(timestamp_str)

                if timestamp:
                    if first_event_ts is None or timestamp < first_event_ts:
                        first_event_ts = timestamp
                    if last_event_ts is None or timestamp > last_event_ts:
                        last_event_ts = timestamp

                if record_type == "session_meta":
                    session_id = payload.get("id", session_id)
                    cwd = payload.get("cwd", cwd)
                    cli_version = payload.get("cli_version", cli_version)
                    started_at = parse_iso(payload.get("timestamp")) or started_at
                elif record_type == "turn_context":
                    model = payload.get("model", model)
                elif (
                    record_type == ("event_msg")
                    and payload.get("type") == "token_count"
                ):
                    info = payload.get("info") or {}
                    usage = info.get("last_token_usage") or {}

                    # Deduplicate or just use deterministic ID
                    event_id = self._deterministic_id(
                        f"{path.name}:{timestamp_str}:{line}"
                    )

                    token_records.append(
                        TokenUsageRecord(
                            provider_id=self.provider_id,
                            external_session_id=session_id or path.stem,
                            external_event_id=event_id,
                            timestamp=timestamp or datetime.now(UTC),
                            model_name=model or "unknown",
                            input_tokens=int(usage.get("input_tokens") or 0),
                            output_tokens=int(usage.get("output_tokens") or 0),
                            cached_tokens=int(
                                usage.get("cached_input_tokens")
                                or (usage.get("input_tokens_details") or {}).get(
                                    "cached_tokens"
                                )
                                or 0
                            ),
                            reasoning_tokens=int(
                                usage.get("reasoning_output_tokens")
                                or (usage.get("output_tokens_details") or {}).get(
                                    "reasoning_tokens"
                                )
                                or 0
                            ),
                            total_tokens=int(usage.get("total_tokens") or 0),
                            raw_data=usage,
                        )
                    )

                    rl = payload.get("rate_limits")
                    if rl:
                        quota_records.extend(
                            self._parse_rate_limits(rl, timestamp or datetime.now(UTC))
                        )

        yield SessionRecord(
            provider_id=self.provider_id,
            external_session_id=session_id or path.stem,
            model_name=model or "unknown",
            project_path=cwd,
            project_name=Path(cwd).name if cwd else None,
            created_at=started_at or first_event_ts,
            last_seen_at=last_event_ts,
            metadata={
                "cli_version": cli_version,
                "file_path": str(path),
            },
        )
        yield from token_records
        yield from quota_records

    def _parse_rate_limits(
        self, rl: dict[str, Any], timestamp: datetime
    ) -> list[QuotaRecord]:
        """Parse rate limit information from a session record."""
        records = []
        for key in ["primary", "secondary"]:
            window = rl.get(key)
            if not isinstance(window, dict):
                continue

            used_percent = window.get("used_percent")
            if used_percent is None:
                continue

            records.append(
                QuotaRecord(
                    provider_id=self.provider_id,
                    quota_name=key,
                    timestamp=timestamp,
                    used_percent=float(used_percent),
                    remaining_percent=None,  # Computed
                    window_minutes=window.get("window_minutes"),
                    resets_at=parse_iso(window.get("resets_at_iso"))
                    or (
                        datetime.fromtimestamp(window["resets_at"], tz=UTC)
                        if window.get("resets_at")
                        else None
                    ),
                    source="local_log",
                    raw_data=window,
                )
            )
        return records

    def _sync_state_db(
        self, home: Path, sync_state: dict[str, Any] | None = None
    ) -> Iterable[SessionRecord | TokenUsageRecord]:
        """Sync from state_5.sqlite."""
        db_path = home / "state_5.sqlite"
        if not db_path.exists():
            return

        last_updated = 0
        if sync_state:
            last_updated = sync_state.get(f"{db_path}:last_updated", 0)

        try:
            con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            con.row_factory = sqlite3.Row
            cur = con.cursor()

            query = "SELECT * FROM threads WHERE updated_at > ? ORDER BY updated_at ASC"
            for row in cur.execute(query, (last_updated,)):
                updated_at = row["updated_at"]
                session_id = row["id"]

                yield SessionRecord(
                    provider_id=self.provider_id,
                    external_session_id=session_id,
                    model_name=row["model"] or "unknown",
                    project_path=row["cwd"],
                    project_name=Path(row["cwd"]).name if row["cwd"] else None,
                    created_at=datetime.fromtimestamp(row["created_at"], tz=UTC),
                    last_seen_at=datetime.fromtimestamp(updated_at, tz=UTC),
                    metadata={
                        "title": row["title"],
                        "cli_version": row["cli_version"],
                        "source": "state_5.sqlite",
                    },
                )

                if row["tokens_used"]:
                    event_id = self._deterministic_id(
                        f"state_5:{session_id}:{updated_at}"
                    )
                    yield TokenUsageRecord(
                        provider_id=self.provider_id,
                        external_session_id=session_id,
                        external_event_id=event_id,
                        timestamp=datetime.fromtimestamp(updated_at, tz=UTC),
                        model_name=row["model"] or "unknown",
                        total_tokens=int(row["tokens_used"]),
                        raw_data=dict(row),
                    )

                if sync_state:
                    sync_state[f"{db_path}:last_updated"] = updated_at

            con.close()
        except sqlite3.Error:
            logger.exception("Error reading Codex state_5.sqlite")

    def _sync_logs_db(
        self, home: Path, sync_state: dict[str, Any] | None = None
    ) -> Iterable[TokenUsageRecord]:
        """Sync from logs_2.sqlite."""
        db_path = home / "logs_2.sqlite"
        if not db_path.exists():
            return

        last_ts = 0
        if sync_state:
            last_ts = sync_state.get(f"{db_path}:last_ts", 0)

        try:
            con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            con.row_factory = sqlite3.Row
            cur = con.cursor()

            query = (
                "SELECT * FROM logs WHERE ts > ? AND feedback_log_body "
                "LIKE 'Received message %' ORDER BY ts ASC"
            )
            for row in cur.execute(query, (last_ts,)):
                ts = row["ts"]
                body = row["feedback_log_body"]
                try:
                    payload = json.loads(body[len("Received message ") :])
                except json.JSONDecodeError:
                    continue

                if payload.get("type") != "response.completed":
                    continue

                response = payload.get("response") or {}
                usage = response.get("usage")
                if not usage:
                    continue

                model = response.get("model") or "unknown"
                # logs_2 doesn't have a session ID directly in the log row usually,
                # but we can maybe extract it from somewhere if needed.
                # For now, use a generic session ID or hash.
                session_id = payload.get("conversation_id") or "logs_2_session"
                event_id = self._deterministic_id(f"logs_2:{row['id']}:{ts}")

                yield TokenUsageRecord(
                    provider_id=self.provider_id,
                    external_session_id=session_id,
                    external_event_id=event_id,
                    timestamp=datetime.fromtimestamp(ts, tz=UTC),
                    model_name=model,
                    input_tokens=int(usage.get("input_tokens") or 0),
                    output_tokens=int(usage.get("output_tokens") or 0),
                    cached_tokens=int(
                        (usage.get("input_tokens_details") or {}).get("cached_tokens")
                        or 0
                    ),
                    reasoning_tokens=int(
                        (usage.get("output_tokens_details") or {}).get(
                            "reasoning_tokens"
                        )
                        or 0
                    ),
                    total_tokens=int(usage.get("total_tokens") or 0),
                    raw_data=usage,
                )

                if sync_state:
                    sync_state[f"{db_path}:last_ts"] = ts

            con.close()
        except sqlite3.Error:
            logger.exception("Error reading Codex logs_2.sqlite")

    def _parse_wham_usage(self, data: dict[str, Any]) -> Iterable[QuotaRecord]:
        """Parse WHAM usage response."""
        if not isinstance(data, dict):
            return

        rl = data.get("rate_limit")
        if not isinstance(rl, dict):
            return

        timestamp = datetime.now(UTC)
        for key in ["primary_window", "secondary_window"]:
            window = rl.get(key)
            if not isinstance(window, dict):
                continue

            used_percent = window.get("used_percent")
            if used_percent is None:
                continue

            quota_name = "primary" if key == "primary_window" else "secondary"
            limit_window_seconds = window.get("limit_window_seconds")
            reset_after_seconds = window.get("reset_after_seconds")

            resets_at = None
            if reset_after_seconds is not None:
                resets_at = datetime.fromtimestamp(
                    timestamp.timestamp() + reset_after_seconds, tz=UTC
                )

            yield QuotaRecord(
                provider_id=self.provider_id,
                quota_name=quota_name,
                timestamp=timestamp,
                used_percent=float(used_percent),
                remaining_percent=None,
                window_minutes=(
                    limit_window_seconds // 60 if limit_window_seconds else None
                ),
                resets_at=resets_at,
                source="active_probe",
                raw_data=window,
            )

    def _deterministic_id(self, key: str) -> str:
        """Create a deterministic ID."""
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    def _ssl_context(self) -> ssl.SSLContext:
        """Create a SSL context with CA certificates."""
        for env_name in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE"):
            env_path = os.environ.get(env_name)
            if env_path and Path(env_path).exists():
                return ssl.create_default_context(cafile=env_path)
        return ssl.create_default_context()

    def _http_get_json(
        self,
        url: str,
        *,
        bearer_token: str | None = None,
        timeout_seconds: int = 20,
    ) -> dict[str, Any]:
        """Perform a JSON GET request."""
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "*/*",
        }
        if bearer_token:
            headers["Authorization"] = f"Bearer {bearer_token}"

        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(
                request,
                timeout=timeout_seconds,
                context=self._ssl_context(),
            ) as response:
                payload = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            payload = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code}: {payload[:1000]}") from exc

        if not payload.strip():
            return {}
        data = json.loads(payload)
        if isinstance(data, dict):
            return data
        return {"value": data}
