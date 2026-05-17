"""HTTP route registration on a FastAPI app."""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException

from quota_tracker import __version__
from quota_tracker.api.schemas import (
    ConfigPatchRequest,
    ProviderActionRequest,
    ProviderPatchRequest,
)
from quota_tracker.config import AppConfig, ModelPricing, save_config
from quota_tracker.daemon import DaemonService
from quota_tracker.db import (
    apply_migrations,
    connect_db,
    list_provider_health,
    list_provider_rows,
    update_provider_row,
)

_GROUP_BY_EXPR: dict[str, str] = {
    "provider": "provider_id",
    "model": "model_name",
    "session": "session_id",
    "day": "substr(timestamp, 1, 10)",
    "hour": "substr(timestamp, 1, 13)",
}


def _build_cost_exprs(pricing: dict[str, ModelPricing]) -> dict[str, str]:
    """Build SQL expressions for total, input, output, and cached costs."""

    cases_total = []
    cases_input = []
    cases_output = []
    cases_cached = []
    for key, p in pricing.items():
        if ":" not in key:
            continue
        pid, model = key.split(":", 1)
        m_esc = model.replace("'", "''").lower()
        p_esc = pid.replace("'", "''").lower()
        cond = f"WHEN LOWER(provider_id) = '{p_esc}' AND LOWER(model_name) = '{m_esc}' THEN "
        input_tokens_expr = (
            "max(input_tokens - cached_tokens, 0)" if p_esc == "codex" else "input_tokens"
        )
        cases_total.append(
            f"{cond} ({input_tokens_expr} * {p.input_1m} + "
            f"cached_tokens * {p.cached_1m} + "
            f"output_tokens * {p.output_1m}) / 1000000.0"
        )
        cases_input.append(f"{cond} ({input_tokens_expr} * {p.input_1m}) / 1000000.0")
        cases_output.append(f"{cond} (output_tokens * {p.output_1m}) / 1000000.0")
        cases_cached.append(f"{cond} (cached_tokens * {p.cached_1m}) / 1000000.0")

    def make_case(cases: list[str], alias: str) -> str:
        if not cases:
            return f"0.0 as {alias}"
        return "SUM(CASE " + " ".join(cases) + f" ELSE 0.0 END) as {alias}"

    return {
        "estimated_cost": make_case(cases_total, "estimated_cost"),
        "input_cost": make_case(cases_input, "input_cost"),
        "output_cost": make_case(cases_output, "output_cost"),
        "cached_cost": make_case(cases_cached, "cached_cost"),
    }


def _input_tokens_sum_expr() -> str:
    """Return billable non-cached input tokens for providers where cache is a subset."""

    return (
        "SUM(CASE "
        "WHEN LOWER(provider_id) = 'codex' THEN max(input_tokens - cached_tokens, 0) "
        "ELSE input_tokens END) as input_tokens"
    )


def _normalize_iso_param(value: str | None) -> str | None:
    """Normalize ISO timestamps coming from the frontend for safe TEXT comparisons.

    We store timestamps as TEXT (Python isoformat with +00:00). Some clients send RFC3339 "Z"
    and/or milliseconds. String comparisons like `timestamp >= ?` can break if formats differ.
    """

    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        # Accept "...Z" and milliseconds.
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return raw
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    dt = dt.astimezone(UTC).replace(microsecond=0)
    return dt.isoformat()


def _health_payload(db_path: Path, scheduler_enabled: bool) -> dict[str, object]:
    """Build the /api/health response."""

    conn = connect_db(str(db_path))
    try:
        apply_migrations(conn)
        providers = list_provider_health(conn)
    finally:
        conn.close()
    return {
        "status": "ok",
        "database": {"path": str(db_path), "migrated": True},
        "scheduler": {"enabled": scheduler_enabled},
        "providers": providers,
    }


def register_routes(
    app: FastAPI,
    *,
    db_path: Path,
    config: AppConfig,
    config_path_str: str | None,
    service: DaemonService | None,
) -> None:
    """Wire all /api endpoints onto the given FastAPI app."""

    @app.get("/api/health")
    def health() -> dict[str, object]:
        """Return health status, DB, scheduler, and provider summary."""

        return _health_payload(db_path, service is not None)

    @app.get("/api/providers")
    def providers() -> dict[str, Any]:
        """Return provider health and safe config."""

        conn = connect_db(str(db_path))
        try:
            apply_migrations(conn)
            return {"providers": list_provider_health(conn)}
        finally:
            conn.close()

    @app.patch("/api/providers/{provider_id}")
    def patch_provider(provider_id: str, payload: ProviderPatchRequest) -> dict[str, Any]:
        """Patch one provider configuration in DB."""

        if provider_id not in {"gemini", "codex", "copilot", "claude"}:
            raise HTTPException(status_code=404, detail="provider not found")
        conn = connect_db(str(db_path))
        try:
            apply_migrations(conn)
            rows = {row["id"]: row for row in list_provider_rows(conn)}
            row = rows.get(provider_id)
            if row is None:
                raise HTTPException(status_code=404, detail="provider not found")
            cfg = dict(row["config"])
            if payload.home_path is not None:
                cfg["home_path"] = payload.home_path
            cfg["active_probe_enabled"] = True
            if payload.passive_sync_enabled is not None:
                cfg["passive_sync_enabled"] = payload.passive_sync_enabled
            enabled = row["enabled"] if payload.enabled is None else payload.enabled
            update_provider_row(conn, provider_id, enabled=enabled, config=cfg)
            conn.commit()
            return {"ok": True}
        finally:
            conn.close()

    @app.post("/api/providers/{provider_id}/scan")
    def manual_scan(provider_id: str, payload: ProviderActionRequest) -> dict[str, Any]:
        """Run manual passive scan for one provider."""

        runner = service or DaemonService(str(db_path))
        summary = runner.run_scan(provider=provider_id, full=payload.full_rescan)
        return {"ok": True, "summary": summary.__dict__}

    @app.post("/api/providers/{provider_id}/probe")
    def manual_probe(provider_id: str) -> dict[str, Any]:
        """Run manual active probe for one provider."""

        runner = service or DaemonService(str(db_path))
        summary = runner.run_probe(provider=provider_id)
        return {"ok": True, "summary": summary.__dict__}

    @app.post("/api/providers/{provider_id}/rescan")
    def manual_full_rescan(provider_id: str, payload: ProviderActionRequest) -> dict[str, Any]:
        """Reset high-water marks then run full rescan when explicitly requested."""

        if not payload.full_rescan:
            return {
                "ok": False,
                "error": "full_rescan confirmation required",
            }
        runner = service or DaemonService(str(db_path))
        runner.reset_high_water_marks(provider_id)
        summary = runner.run_scan(provider=provider_id, full=True)
        return {"ok": True, "summary": summary.__dict__}

    @app.get("/api/quotas")
    def quotas(
        provider_id: str | None = None,
        quota_name: str | None = None,
        start: str | None = None,
        end: str | None = None,
        limit: int = 1000,
        order: str = "desc",
        downsample: int | None = None,
    ) -> dict[str, Any]:
        """Return filtered quota history with optional server-side downsampling."""

        start_iso = _normalize_iso_param(start)
        end_iso = _normalize_iso_param(end)
        if order not in ("asc", "desc"):
            raise HTTPException(status_code=400, detail="order must be 'asc' or 'desc'")
        conn = connect_db(str(db_path))
        try:
            apply_migrations(conn)

            # Define a base query that combines high-res and archived history.
            # We use NULL for columns present in one but not the other to keep the UNION compatible.
            combined_base = """
                SELECT 
                    provider_id, quota_name, source, timestamp, 
                    used_percent, remaining_percent, window_minutes, resets_at, raw_data 
                FROM quota_history
                UNION ALL
                SELECT 
                    provider_id, quota_name, 'archive' as source, timestamp,
                    used_percent, remaining_percent, window_minutes, 
                    NULL as resets_at, NULL as raw_data
                FROM quota_history_archived
            """

            # If downsample is requested (e.g., target 200 points), we aggregate by time buckets.
            if downsample and downsample > 0:
                # Find the actual time range from both tables.
                range_query = f"""
                    SELECT MIN(unixepoch(timestamp)), MAX(unixepoch(timestamp)) 
                    FROM ({combined_base}) as combined WHERE 1=1
                """
                range_params: list[Any] = []
                if provider_id:
                    range_query += " AND provider_id = ?"
                    range_params.append(provider_id)
                if quota_name:
                    range_query += " AND quota_name = ?"
                    range_params.append(quota_name)
                if start_iso:
                    range_query += " AND datetime(timestamp) >= datetime(?)"
                    range_params.append(start_iso)
                if end_iso:
                    range_query += " AND datetime(timestamp) <= datetime(?)"
                    range_params.append(end_iso)

                min_ts, max_ts = conn.execute(range_query, tuple(range_params)).fetchone()
                if min_ts and max_ts and max_ts > min_ts:
                    bucket_seconds = max(1, (max_ts - min_ts) // downsample)
                    ts_expr = (
                        f"datetime((unixepoch(timestamp) / {bucket_seconds}) "
                        f"* {bucket_seconds}, 'unixepoch')"
                    )
                    query = f"""
                        SELECT 
                            provider_id, quota_name, source,
                            {ts_expr} as timestamp,
                            AVG(used_percent) as used_percent,
                            AVG(remaining_percent) as remaining_percent,
                            MAX(window_minutes) as window_minutes,
                            MAX(resets_at) as resets_at,
                            NULL as raw_data
                        FROM ({combined_base}) as combined WHERE 1=1
                    """
                    params: list[Any] = []
                    if provider_id:
                        query += " AND provider_id = ?"
                        params.append(provider_id)
                    if quota_name:
                        query += " AND quota_name = ?"
                        params.append(quota_name)
                    if start_iso:
                        query += " AND datetime(timestamp) >= datetime(?)"
                        params.append(start_iso)
                    if end_iso:
                        query += " AND datetime(timestamp) <= datetime(?)"
                        params.append(end_iso)

                    query += " GROUP BY provider_id, quota_name, (unixepoch(timestamp) / ?)"
                    params.append(bucket_seconds)
                    query += f" ORDER BY timestamp {order.upper()} LIMIT ?"
                    params.append(limit)

                    rows = conn.execute(query, tuple(params)).fetchall()
                    return {"items": [dict(row) for row in rows], "downsampled": True}

            # Default raw fetch if no downsampling requested.
            raw_query = f"SELECT * FROM ({combined_base}) as combined WHERE 1=1"
            raw_params: list[Any] = []
            if provider_id:
                raw_query += " AND provider_id = ?"
                raw_params.append(provider_id)
            if quota_name:
                raw_query += " AND quota_name = ?"
                raw_params.append(quota_name)
            if start_iso:
                raw_query += " AND datetime(timestamp) >= datetime(?)"
                raw_params.append(start_iso)
            if end_iso:
                raw_query += " AND datetime(timestamp) <= datetime(?)"
                raw_params.append(end_iso)
            direction = "ASC" if order == "asc" else "DESC"
            raw_query += f" ORDER BY datetime(timestamp) {direction} LIMIT ?"
            raw_params.append(limit)
            rows = conn.execute(raw_query, tuple(raw_params)).fetchall()
            items = []
            for row in rows:
                d = dict(row)
                if d.get("raw_data"):
                    try:
                        d["raw_data"] = json.loads(d["raw_data"])
                    except json.JSONDecodeError:
                        d["raw_data"] = {}
                else:
                    d["raw_data"] = {}
                items.append(d)
            return {"items": items}
        finally:
            conn.close()

    @app.get("/api/token-usage/by-project")
    def token_usage_by_project(
        provider_id: str | None = None,
        start: str | None = None,
        end: str | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Return token usage aggregated by project_path."""

        start = _normalize_iso_param(start)
        end = _normalize_iso_param(end)
        conn = connect_db(str(db_path))
        try:
            apply_migrations(conn)
            where = "WHERE s.project_path IS NOT NULL"
            params: list[Any] = []
            if provider_id:
                where += " AND t.provider_id = ?"
                params.append(provider_id)
            if start:
                where += " AND datetime(t.timestamp) >= datetime(?)"
                params.append(start)
            if end:
                where += " AND datetime(t.timestamp) <= datetime(?)"
                params.append(end)
            count_row = conn.execute(
                f"SELECT COUNT(DISTINCT CASE WHEN s.project_name = 'repo' "
                f"OR s.project_path LIKE '%/repo' THEN 'repo' ELSE s.project_path END) "
                f"FROM token_usage_history t JOIN sessions s ON t.session_id = s.id {where}",
                tuple(params),
            ).fetchone()
            total_projects = count_row[0] if count_row else 0

            total_tokens_row = conn.execute(
                f"SELECT SUM(t.total_tokens) "
                f"FROM token_usage_history t JOIN sessions s ON t.session_id = s.id {where}",
                tuple(params),
            ).fetchone()
            global_total_tokens = (
                total_tokens_row[0] if total_tokens_row and total_tokens_row[0] else 0
            )

            rows = conn.execute(
                f"SELECT "
                f"CASE WHEN s.project_name = 'repo' OR s.project_path LIKE '%/repo' "
                f"THEN 'Multiple Repos' ELSE s.project_path END as project_path, "
                f"CASE WHEN s.project_name = 'repo' OR s.project_path LIKE '%/repo' "
                f"THEN 'repo' ELSE s.project_name END as project_name, "
                f"SUM(t.total_tokens) as total_tokens, "
                f"COUNT(DISTINCT t.session_id) as session_count "
                f"FROM token_usage_history t JOIN sessions s ON t.session_id = s.id {where} "
                f"GROUP BY CASE WHEN s.project_name = 'repo' OR s.project_path LIKE '%/repo' "
                f"THEN 'repo' ELSE s.project_path END "
                f"ORDER BY total_tokens DESC LIMIT ? OFFSET ?",
                tuple(params) + (limit, offset),
            ).fetchall()
            return {
                "items": [dict(row) for row in rows],
                "total": total_projects,
                "total_tokens": global_total_tokens,
            }
        finally:
            conn.close()

    @app.get("/api/sessions")
    def sessions(
        provider_id: str | None = None,
        project_name: str | None = None,
        model_name: str | None = None,
        start: str | None = None,
        end: str | None = None,
    ) -> dict[str, Any]:
        """Return filtered sessions."""

        start = _normalize_iso_param(start)
        end = _normalize_iso_param(end)
        conn = connect_db(str(db_path))
        try:
            apply_migrations(conn)
            query = "SELECT * FROM sessions WHERE 1=1"
            params: list[Any] = []
            if provider_id:
                query += " AND provider_id = ?"
                params.append(provider_id)
            if project_name:
                query += " AND project_name = ?"
                params.append(project_name)
            if model_name:
                query += " AND model_name = ?"
                params.append(model_name)
            if start:
                query += " AND datetime(last_seen_at) >= datetime(?)"
                params.append(start)
            if end:
                query += " AND datetime(last_seen_at) <= datetime(?)"
                params.append(end)
            query += " ORDER BY last_seen_at DESC"
            rows = conn.execute(query, tuple(params)).fetchall()
            return {"items": [dict(row) for row in rows]}
        finally:
            conn.close()

    @app.get("/api/token-usage")
    def token_usage(
        group_by: str = "provider",
        provider_id: str | None = None,
        start: str | None = None,
        end: str | None = None,
        model_name: str | None = None,
    ) -> dict[str, Any]:
        """Return aggregated token usage with optional time and model filters."""

        start = _normalize_iso_param(start)
        end = _normalize_iso_param(end)
        if group_by not in _GROUP_BY_EXPR:
            raise HTTPException(status_code=400, detail="invalid group_by")
        expr = _GROUP_BY_EXPR[group_by]
        costs = _build_cost_exprs(config.pricing)
        conn = connect_db(str(db_path))
        try:
            apply_migrations(conn)
            query = (
                f"SELECT {expr} as bucket, "
                f"{_input_tokens_sum_expr()}, "
                "SUM(output_tokens) as output_tokens, "
                "SUM(cached_tokens) as cached_tokens, "
                "SUM(reasoning_tokens) as reasoning_tokens, "
                "SUM(thoughts_tokens) as thoughts_tokens, "
                "SUM(tool_tokens) as tool_tokens, "
                "SUM(total_tokens) as total_tokens, "
                f"{costs['estimated_cost']}, "
                f"{costs['input_cost']}, "
                f"{costs['output_cost']}, "
                f"{costs['cached_cost']} "
                "FROM token_usage_history WHERE 1=1"
            )
            params: list[Any] = []
            if provider_id:
                query += " AND provider_id = ?"
                params.append(provider_id)
            if model_name:
                query += " AND model_name = ?"
                params.append(model_name)
            if start:
                query += " AND datetime(timestamp) >= datetime(?)"
                params.append(start)
            if end:
                query += " AND datetime(timestamp) <= datetime(?)"
                params.append(end)
            query += " GROUP BY bucket ORDER BY bucket"
            rows = conn.execute(query, tuple(params)).fetchall()
            return {"items": [dict(row) for row in rows], "group_by": group_by}
        finally:
            conn.close()

    @app.get("/api/config")
    def get_config() -> dict[str, Any]:
        """Return sanitized app config."""

        return {"config": config.model_dump()}

    @app.patch("/api/config")
    def patch_config(payload: ConfigPatchRequest) -> dict[str, Any]:
        """Patch and persist global config."""

        if payload.sync_interval_minutes is not None:
            if payload.sync_interval_minutes <= 0:
                raise HTTPException(status_code=400, detail="invalid sync interval")
            config.daemon.sync_interval_minutes = payload.sync_interval_minutes
        if payload.active_probe_interval_minutes is not None:
            if payload.active_probe_interval_minutes <= 0:
                raise HTTPException(status_code=400, detail="invalid active interval")
            config.daemon.active_probe_interval_minutes = payload.active_probe_interval_minutes
        if payload.passive_sync_interval_minutes is not None:
            if payload.passive_sync_interval_minutes <= 0:
                raise HTTPException(status_code=400, detail="invalid passive interval")
            config.daemon.passive_sync_interval_minutes = payload.passive_sync_interval_minutes
        if payload.web_host is not None:
            config.daemon.web_host = payload.web_host
        if payload.web_port is not None:
            if payload.web_port < 1 or payload.web_port > 65535:
                raise HTTPException(status_code=400, detail="invalid port")
            config.daemon.web_port = payload.web_port
        if payload.database_path is not None:
            config.daemon.database_path = payload.database_path
        if payload.log_level is not None:
            config.daemon.log_level = payload.log_level
        if payload.pricing is not None:
            config.pricing = payload.pricing
        save_config(config, config_path_str)
        return {"config": config.model_dump()}

    def _detect_install_method() -> str:
        import sys as _sys

        if "/nix/store/" in _sys.executable:
            return "nix"
        return "curl"

    @app.get("/api/version")
    async def get_version() -> dict[str, Any]:
        """Return current version and latest available release from GitHub."""

        latest: str | None = None
        update_available = False
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(
                    "https://api.github.com/repos/Thomas97460/quota-tracker/releases/latest",
                    headers={"Accept": "application/vnd.github+json"},
                )
                if r.status_code == 200:
                    latest = r.json().get("tag_name", "").lstrip("v") or None
                    is_dev = "dev" in __version__
                    if latest and not is_dev:
                        update_available = latest != __version__
        except Exception:
            pass
        return {
            "current": __version__,
            "latest": latest,
            "update_available": update_available,
            "install_method": _detect_install_method(),
        }

    @app.post("/api/update")
    def trigger_update() -> dict[str, str]:
        """Spawn install.sh outside the service cgroup so it survives the service restart."""

        systemd_run = shutil.which("systemd-run")
        if not systemd_run:
            raise HTTPException(status_code=503, detail="systemd-run is not available")

        install_cmd = (
            "INTERACTIVE=0 RESTART_SERVICE=1 curl -fsSL "
            "https://raw.githubusercontent.com/Thomas97460/quota-tracker/main/install.sh "
            "| bash"
        )
        unit_name = f"quota-tracker-updater-{time.time_ns()}"
        result = subprocess.run(
            [
                systemd_run,
                "--user",
                "--collect",
                f"--unit={unit_name}",
                "--description=quota-tracker self-update",
                "bash",
                "-c",
                install_cmd,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "failed to start updater").strip()
            raise HTTPException(status_code=503, detail=detail[-500:])
        return {"status": "updating", "unit": unit_name}
