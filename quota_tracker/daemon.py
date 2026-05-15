"""Daemon sync scheduler and manual sync/probe operations."""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from quota_tracker.db import (
    TokenUsageRecord,
    apply_migrations,
    connect_db,
    get_provider_row,
    insert_quota,
    insert_token_usage,
    list_provider_rows,
    run_maintenance,
    update_provider_row,
    upsert_session,
    write_transaction,
)
from quota_tracker.logging import configure_logging, log_operation
from quota_tracker.providers import (
    ClaudeAiProvider,
    CodexProvider,
    CopilotProvider,
    GeminiProvider,
    Provider,
)

LOGGER = logging.getLogger(__name__)
PROVIDERS = ("gemini", "codex", "copilot", "claude")
AUTO_PROBE_PROVIDERS = ("gemini", "codex", "copilot", "claude")


@dataclass(frozen=True)
class SyncSummary:
    """Summary of one sync/probe run."""

    providers: list[str]
    sessions_upserted: int
    token_rows_inserted: int
    quota_rows_inserted: int
    parse_failures: int
    failed_providers: list[str]


class DaemonService:
    """Own provider orchestration for scan/probe and scheduler ticks."""

    def __init__(
        self,
        db_path: str,
        sync_interval_minutes: int = 5,
        passive_sync_interval_minutes: int | None = None,
        active_probe_interval_minutes: int | None = None,
        log_level: str = "INFO",
    ) -> None:
        """Initialize daemon service settings."""

        self.db_path = db_path
        self.sync_interval_minutes = sync_interval_minutes
        self.passive_sync_interval_minutes = passive_sync_interval_minutes or sync_interval_minutes
        self.active_probe_interval_minutes = active_probe_interval_minutes or sync_interval_minutes
        configure_logging(log_level)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def migrate_and_prepare(self) -> None:
        """Apply migrations and ensure default providers exist."""

        conn = connect_db(self.db_path)
        try:
            apply_migrations(conn)
        finally:
            conn.close()
        LOGGER.info(
            json.dumps(
                {
                    "operation": "startup",
                    "db_path": self.db_path,
                    "sync_interval_minutes": self.sync_interval_minutes,
                    "passive_sync_interval_minutes": self.passive_sync_interval_minutes,
                    "active_probe_interval_minutes": self.active_probe_interval_minutes,
                },
                ensure_ascii=True,
            )
        )

    def _provider_instance(self, provider_id: str, config: dict[str, Any]) -> Provider:
        """Build one provider instance from persisted provider config."""

        home = str(config.get("home_path", f"~/.{provider_id}"))
        if provider_id == "gemini":
            safe_options = config.get("safe_options", {})
            project_id = None
            if isinstance(safe_options, dict):
                for key in (
                    "google_cloud_project",
                    "google_cloud_project_id",
                    "cloudaicompanion_project",
                ):
                    value = safe_options.get(key)
                    if isinstance(value, str) and value.strip():
                        project_id = value
                        break
            return GeminiProvider(home=home, project_id=project_id)
        if provider_id == "codex":
            include_archived = bool(config.get("safe_options", {}).get("include_archived", True))
            return CodexProvider(home=home, include_archived=include_archived)
        if provider_id == "copilot":
            return CopilotProvider(home=home)
        if provider_id == "claude":
            return ClaudeAiProvider(home=home)
        raise ValueError(f"unsupported provider_id: {provider_id}")

    def _provider_ids(self, provider: str) -> list[str]:
        """Resolve provider selector to explicit provider id list."""

        if provider == "all":
            return list(PROVIDERS)
        if provider not in PROVIDERS:
            raise ValueError(f"unsupported provider: {provider}")
        return [provider]

    def _set_scan_state(
        self, conn: Any, row: dict[str, Any], *, marks: dict[str, Any], parse_failures: int
    ) -> None:
        """Persist high-water marks and last scan state."""

        config = dict(row["config"])
        safe = dict(config.get("safe_options", {}))
        safe["last_successful_sync_at"] = datetime.now(UTC).isoformat()
        safe["last_parse_failures"] = parse_failures
        config["safe_options"] = safe
        config["high_water_marks"] = marks
        update_provider_row(conn, row["id"], enabled=row["enabled"], config=config)

    def _set_probe_state(
        self,
        conn: Any,
        row: dict[str, Any],
        *,
        success: bool,
        message: str | None = None,
    ) -> None:
        """Persist last probe health state."""

        config = dict(row["config"])
        safe = dict(config.get("safe_options", {}))
        safe["last_probe_attempted_at"] = datetime.now(UTC).isoformat()
        if success:
            safe["last_successful_probe_at"] = safe["last_probe_attempted_at"]
            safe.pop("last_probe_error", None)
        else:
            safe["last_probe_error"] = message or "probe failed"
        config["safe_options"] = safe
        update_provider_row(conn, row["id"], enabled=row["enabled"], config=config)

    def run_scan(self, provider: str = "all", full: bool = False) -> SyncSummary:
        """Run manual passive sync for one provider or all providers."""

        selected = self._provider_ids(provider)
        conn = connect_db(self.db_path)
        sessions_upserted = 0
        token_rows_inserted = 0
        quota_rows_inserted = 0
        parse_failures = 0
        failed: list[str] = []
        try:
            apply_migrations(conn)
            rows = {row["id"]: row for row in list_provider_rows(conn)}
            for provider_id in selected:
                row = rows[provider_id]
                if not row["enabled"]:
                    continue
                started = time.time()
                try:
                    provider_impl = self._provider_instance(provider_id, row["config"])
                    marks = row["config"].get("high_water_marks", {})
                    result = (
                        provider_impl.passive_scan_full()
                        if full
                        else provider_impl.passive_scan_incremental(marks)
                    )
                    with write_transaction(conn):
                        for session in result.sessions:
                            session_id = upsert_session(conn, session)
                            sessions_upserted += 1
                            for item in result.token_usage:
                                if item["external_session_id"] != session.external_session_id:
                                    continue
                                insert_token_usage(
                                    conn,
                                    TokenUsageRecord(
                                        provider_id=item["provider_id"],
                                        session_id=session_id,
                                        external_event_id=item["external_event_id"],
                                        timestamp=item["timestamp"],
                                        model_name=item["model_name"],
                                        source=item["source"],
                                        input_tokens=item["input_tokens"],
                                        output_tokens=item["output_tokens"],
                                        cached_tokens=item["cached_tokens"],
                                        reasoning_tokens=item["reasoning_tokens"],
                                        thoughts_tokens=item["thoughts_tokens"],
                                        tool_tokens=item["tool_tokens"],
                                        total_tokens=item["total_tokens"],
                                        raw_data=item["raw_metadata"],
                                    ),
                                )
                                token_rows_inserted += 1
                        for quota in result.quotas:
                            insert_quota(conn, quota)
                            quota_rows_inserted += 1
                        self._set_scan_state(
                            conn,
                            row,
                            marks=result.high_water_marks,
                            parse_failures=result.parse_failures,
                        )
                    parse_failures += result.parse_failures
                    log_operation(
                        LOGGER,
                        provider_id=provider_id,
                        operation="passive_scan",
                        outcome="ok",
                        started_at=started,
                    )
                except Exception as exc:  # pragma: no cover - safety behavior
                    failed.append(provider_id)
                    log_operation(
                        LOGGER,
                        provider_id=provider_id,
                        operation="passive_scan",
                        outcome="error",
                        started_at=started,
                        error_summary=str(exc),
                    )
            return SyncSummary(
                providers=selected,
                sessions_upserted=sessions_upserted,
                token_rows_inserted=token_rows_inserted,
                quota_rows_inserted=quota_rows_inserted,
                parse_failures=parse_failures,
                failed_providers=failed,
            )
        finally:
            conn.close()

    def run_probe(self, provider: str = "all") -> SyncSummary:
        """Run manual active quota probing for one provider or all providers."""

        selected = self._provider_ids(provider)
        conn = connect_db(self.db_path)
        quota_rows_inserted = 0
        failed: list[str] = []
        try:
            apply_migrations(conn)
            rows = {row["id"]: row for row in list_provider_rows(conn)}
            for provider_id in selected:
                row = rows[provider_id]
                if not row["enabled"]:
                    continue
                started = time.time()
                try:
                    provider_impl = self._provider_instance(provider_id, row["config"])
                    quotas = provider_impl.active_probe()
                    with write_transaction(conn):
                        for quota in quotas:
                            insert_quota(conn, quota)
                            quota_rows_inserted += 1
                        self._set_probe_state(conn, row, success=True)
                    log_operation(
                        LOGGER,
                        provider_id=provider_id,
                        operation="active_probe",
                        outcome="ok",
                        started_at=started,
                    )
                except Exception as exc:  # pragma: no cover - safety behavior
                    failed.append(provider_id)
                    with write_transaction(conn):
                        self._set_probe_state(conn, row, success=False, message=str(exc))
                    log_operation(
                        LOGGER,
                        provider_id=provider_id,
                        operation="active_probe",
                        outcome="error",
                        started_at=started,
                        error_summary=str(exc),
                    )
            return SyncSummary(
                providers=selected,
                sessions_upserted=0,
                token_rows_inserted=0,
                quota_rows_inserted=quota_rows_inserted,
                parse_failures=0,
                failed_providers=failed,
            )
        finally:
            conn.close()

    def tick(self) -> None:
        """Run one scheduler tick using configured sync and probe intervals."""

        conn = connect_db(self.db_path)
        scan_due = False
        probe_due: list[str] = []
        try:
            apply_migrations(conn)
            run_maintenance(conn)
            now = datetime.now(UTC)
            for row in list_provider_rows(conn):
                if not row["enabled"]:
                    continue
                safe = row["config"].get("safe_options", {})
                last_sync = safe.get("last_successful_sync_at")
                if not last_sync:
                    scan_due = True
                else:
                    delta = now - datetime.fromisoformat(last_sync)
                    if delta.total_seconds() >= self.passive_sync_interval_minutes * 60:
                        scan_due = True
                if row["id"] in AUTO_PROBE_PROVIDERS:
                    last_probe = safe.get("last_probe_attempted_at") or safe.get(
                        "last_successful_probe_at"
                    )
                    if not last_probe:
                        probe_due.append(row["id"])
                    else:
                        probe_delta = now - datetime.fromisoformat(last_probe)
                        if probe_delta.total_seconds() >= self.active_probe_interval_minutes * 60:
                            probe_due.append(row["id"])
        finally:
            conn.close()
        if scan_due:
            self.run_scan(provider="all", full=False)
        for provider_id in probe_due:
            self.run_probe(provider=provider_id)

    def start_scheduler(self, sleep_seconds: float = 1.0) -> None:
        """Start background scheduler loop."""

        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()

        def _loop() -> None:
            """Run periodic ticks until the stop event is set."""

            while not self._stop_event.is_set():
                self.tick()
                self._stop_event.wait(sleep_seconds)

        self._thread = threading.Thread(target=_loop, daemon=True)
        self._thread.start()

    def stop_scheduler(self) -> None:
        """Stop background scheduler loop."""

        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    def set_provider_enabled(self, provider_id: str, enabled: bool) -> None:
        """Enable or disable one provider without deleting historical rows."""

        conn = connect_db(self.db_path)
        try:
            apply_migrations(conn)
            row = get_provider_row(conn, provider_id)
            if row is None:
                return
            update_provider_row(conn, provider_id, enabled=enabled, config=row["config"])
            conn.commit()
        finally:
            conn.close()

    def reset_high_water_marks(self, provider_id: str) -> None:
        """Reset one provider high-water marks for an explicit full rescan."""

        conn = connect_db(self.db_path)
        try:
            apply_migrations(conn)
            row = get_provider_row(conn, provider_id)
            if row is None:
                return
            config = dict(row["config"])
            config["high_water_marks"] = {}
            update_provider_row(conn, provider_id, enabled=row["enabled"], config=config)
            conn.commit()
        finally:
            conn.close()
