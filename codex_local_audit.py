#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
import sqlite3
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None  # type: ignore[assignment]


@dataclass
class TokenUsage:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_output_tokens: int = 0
    total_tokens: int = 0

    @classmethod
    def from_mapping(cls, value: dict[str, Any] | None) -> "TokenUsage":
        if not value:
            return cls()

        input_tokens = int(value.get("input_tokens") or 0)
        cached = int(
            value.get("cached_input_tokens")
            or (value.get("input_tokens_details") or {}).get("cached_tokens")
            or 0
        )
        output_tokens = int(value.get("output_tokens") or 0)
        reasoning = int(
            value.get("reasoning_output_tokens")
            or (value.get("output_tokens_details") or {}).get("reasoning_tokens")
            or 0
        )
        total = int(value.get("total_tokens") or (input_tokens + output_tokens))
        return cls(
            input_tokens=input_tokens,
            cached_input_tokens=cached,
            output_tokens=output_tokens,
            reasoning_output_tokens=reasoning,
            total_tokens=total,
        )

    def add(self, other: "TokenUsage") -> None:
        self.input_tokens += other.input_tokens
        self.cached_input_tokens += other.cached_input_tokens
        self.output_tokens += other.output_tokens
        self.reasoning_output_tokens += other.reasoning_output_tokens
        self.total_tokens += other.total_tokens

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass
class RateWindow:
    used_percent: float | None = None
    window_minutes: int | None = None
    resets_at: int | None = None

    @property
    def remaining_percent(self) -> float | None:
        if self.used_percent is None:
            return None
        return max(0.0, 100.0 - float(self.used_percent))

    def reset_datetime(self) -> str | None:
        if self.resets_at is None:
            return None
        return datetime.fromtimestamp(self.resets_at, tz=UTC).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "used_percent": self.used_percent,
            "remaining_percent": self.remaining_percent,
            "window_minutes": self.window_minutes,
            "resets_at": self.resets_at,
            "resets_at_iso": self.reset_datetime(),
        }


@dataclass
class RateLimits:
    limit_id: str | None = None
    limit_name: str | None = None
    plan_type: str | None = None
    rate_limit_reached_type: str | None = None
    credits: dict[str, Any] | None = None
    primary: RateWindow = field(default_factory=RateWindow)
    secondary: RateWindow = field(default_factory=RateWindow)

    @classmethod
    def from_mapping(cls, value: dict[str, Any] | None) -> "RateLimits":
        value = value or {}
        primary = value.get("primary") or {}
        secondary = value.get("secondary") or {}
        return cls(
            limit_id=value.get("limit_id"),
            limit_name=value.get("limit_name"),
            plan_type=value.get("plan_type"),
            rate_limit_reached_type=value.get("rate_limit_reached_type"),
            credits=value.get("credits"),
            primary=RateWindow(
                used_percent=primary.get("used_percent"),
                window_minutes=primary.get("window_minutes"),
                resets_at=primary.get("resets_at"),
            ),
            secondary=RateWindow(
                used_percent=secondary.get("used_percent"),
                window_minutes=secondary.get("window_minutes"),
                resets_at=secondary.get("resets_at"),
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "limit_id": self.limit_id,
            "limit_name": self.limit_name,
            "plan_type": self.plan_type,
            "rate_limit_reached_type": self.rate_limit_reached_type,
            "credits": self.credits,
            "primary": self.primary.to_dict(),
            "secondary": self.secondary.to_dict(),
        }


def parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def fmt_int(value: int | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:,}".replace(",", " ")


def fmt_float(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}"


def format_path_size(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "path": str(path)}
    stat = path.stat()
    return {
        "exists": True,
        "path": str(path),
        "size_bytes": stat.st_size,
        "mtime": datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
    }


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def decode_jwt_payload(token: str | None) -> dict[str, Any] | None:
    if not token or token.count(".") < 2:
        return None
    try:
        payload_part = token.split(".")[1]
        padding = "=" * ((4 - len(payload_part) % 4) % 4)
        raw = base64.urlsafe_b64decode(payload_part + padding)
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None


CHATGPT_BACKEND_URL = "https://chatgpt.com/backend-api/wham/usage"


def _ssl_context() -> ssl.SSLContext:
    for env_name in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE"):
        env_path = os.environ.get(env_name)
        if env_path and Path(env_path).exists():
            return ssl.create_default_context(cafile=env_path)

    for ca_path in (
        "/etc/ssl/certs/ca-certificates.crt",
        "/etc/ssl/cert.pem",
        "/etc/pki/tls/certs/ca-bundle.crt",
    ):
        if Path(ca_path).exists():
            return ssl.create_default_context(cafile=ca_path)

    return ssl.create_default_context()


def fetch_wham_usage(access_token: str, timeout_seconds: int = 20) -> dict[str, Any] | None:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "*/*",
    }
    request = urllib.request.Request(CHATGPT_BACKEND_URL, headers=headers)
    try:
        with urllib.request.urlopen(
            request,
            timeout=timeout_seconds,
            context=_ssl_context(),
        ) as response:
            payload = response.read().decode("utf-8", errors="replace")
            return json.loads(payload)
    except Exception:
        return None


def format_seconds(seconds: int | None) -> str:
    if seconds is None:
        return "n/a"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def summarize_auth(codex_home: Path) -> dict[str, Any]:
    auth_path = codex_home / "auth.json"
    data = load_json(auth_path)
    if not data:
        return {"path": str(auth_path), "exists": auth_path.exists(), "loaded": False}

    tokens = data.get("tokens") or {}
    id_payload = decode_jwt_payload(tokens.get("id_token"))
    access_payload = decode_jwt_payload(tokens.get("access_token"))

    auth_claims = ((id_payload or {}).get("https://api.openai.com/auth")) or {}
    access_auth_claims = ((access_payload or {}).get("https://api.openai.com/auth")) or {}

    def exp_iso(payload: dict[str, Any] | None) -> str | None:
        if not payload or payload.get("exp") is None:
            return None
        try:
            return datetime.fromtimestamp(int(payload["exp"]), tz=UTC).isoformat()
        except (TypeError, ValueError, OSError):
            return None

    return {
        "path": str(auth_path),
        "loaded": True,
        "last_refresh": data.get("last_refresh"),
        "account_id": tokens.get("account_id"),
        "token_presence": {
            "id_token": bool(tokens.get("id_token")),
            "access_token": bool(tokens.get("access_token")),
            "refresh_token": bool(tokens.get("refresh_token")),
        },
        "id_token_exp": exp_iso(id_payload),
        "access_token_exp": exp_iso(access_payload),
        "plan_type_from_id_token": auth_claims.get("chatgpt_plan_type"),
        "subscription_active_until": auth_claims.get("chatgpt_subscription_active_until"),
        "plan_type_from_access_token": access_auth_claims.get("chatgpt_plan_type"),
    }


def summarize_config(codex_home: Path) -> dict[str, Any]:
    config_path = codex_home / "config.toml"
    summary: dict[str, Any] = {
        "path": str(config_path),
        "exists": config_path.exists(),
        "loaded": False,
    }
    if not config_path.exists() or tomllib is None:
        return summary

    try:
        config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return summary

    projects = config.get("projects") or {}
    trust_levels: dict[str, int] = {}
    for project_cfg in projects.values():
        trust = (project_cfg or {}).get("trust_level", "unknown")
        trust_levels[trust] = trust_levels.get(trust, 0) + 1

    summary.update(
        {
            "loaded": True,
            "model": config.get("model"),
            "model_reasoning_effort": config.get("model_reasoning_effort"),
            "personality": config.get("personality"),
            "approval_policy": config.get("approval_policy"),
            "sandbox_mode": config.get("sandbox_mode"),
            "web_search": config.get("web_search"),
            "tui": config.get("tui"),
            "features": config.get("features"),
            "projects_count": len(projects),
            "project_trust_levels": trust_levels,
            "plugins": config.get("plugins"),
        }
    )
    return summary


def summarize_files(codex_home: Path, top_n: int) -> dict[str, Any]:
    interesting = [
        codex_home / "config.toml",
        codex_home / "auth.json",
        codex_home / "version.json",
        codex_home / "installation_id",
        codex_home / "history.jsonl",
        codex_home / "session_index.jsonl",
        codex_home / "state_5.sqlite",
        codex_home / "logs_2.sqlite",
        codex_home / "log" / "codex-tui.log",
    ]
    inventory = [format_path_size(p) for p in interesting]

    largest: list[dict[str, Any]] = []
    for path in codex_home.rglob("*"):
        if not path.is_file():
            continue
        stat = path.stat()
        largest.append(
            {
                "path": str(path),
                "size_bytes": stat.st_size,
                "mtime": datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
            }
        )
    largest.sort(key=lambda item: item["size_bytes"], reverse=True)

    return {"interesting_files": inventory, "largest_files": largest[:top_n]}


def iter_session_files(codex_home: Path, include_archived: bool) -> list[Path]:
    files = list((codex_home / "sessions").glob("**/*.jsonl"))
    if include_archived:
        files.extend((codex_home / "archived_sessions").glob("*.jsonl"))
    return sorted(files)


def scan_session_file(path: Path) -> dict[str, Any]:
    session_id = None
    cwd = None
    model = None
    cli_version = None
    started_at = None
    token_events = 0
    event_sum = TokenUsage()
    latest_total: TokenUsage | None = None
    latest_rate_limits: RateLimits | None = None
    latest_rate_limits_ts: str | None = None
    latest_token_event_ts: str | None = None
    first_event_ts: datetime | None = None
    last_event_ts: datetime | None = None
    first_token_count_ts: datetime | None = None
    last_token_count_ts: datetime | None = None
    latest_rate_limits_dt: datetime | None = None

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            record_type = record.get("type")
            payload = record.get("payload") or {}
            timestamp = record.get("timestamp")
            timestamp_dt = parse_iso(timestamp)

            if timestamp_dt is not None:
                if first_event_ts is None or timestamp_dt < first_event_ts:
                    first_event_ts = timestamp_dt
                if last_event_ts is None or timestamp_dt > last_event_ts:
                    last_event_ts = timestamp_dt

            if record_type == "session_meta":
                session_id = payload.get("id", session_id)
                cwd = payload.get("cwd", cwd)
                cli_version = payload.get("cli_version", cli_version)
                started_at = payload.get("timestamp", started_at)
            elif record_type == "turn_context":
                model = payload.get("model", model)

            if record_type != "event_msg" or payload.get("type") != "token_count":
                continue

            token_events += 1
            latest_token_event_ts = timestamp or latest_token_event_ts
            if timestamp_dt is not None:
                if first_token_count_ts is None or timestamp_dt < first_token_count_ts:
                    first_token_count_ts = timestamp_dt
                if last_token_count_ts is None or timestamp_dt > last_token_count_ts:
                    last_token_count_ts = timestamp_dt
            info = payload.get("info") or {}

            event_sum.add(TokenUsage.from_mapping(info.get("last_token_usage")))
            candidate_total = TokenUsage.from_mapping(info.get("total_token_usage"))
            if candidate_total.total_tokens > 0:
                latest_total = candidate_total

            rl = payload.get("rate_limits")
            if rl:
                latest_rate_limits = RateLimits.from_mapping(rl)
                latest_rate_limits_ts = timestamp
                if timestamp_dt is not None and (
                    latest_rate_limits_dt is None or timestamp_dt > latest_rate_limits_dt
                ):
                    latest_rate_limits_dt = timestamp_dt

    effective_usage = latest_total if latest_total and latest_total.total_tokens else event_sum

    return {
        "file": str(path),
        "session_id": session_id or path.stem,
        "cwd": cwd,
        "model": model,
        "cli_version": cli_version,
        "started_at": started_at,
        "token_event_count": token_events,
        "event_sum_usage": event_sum.to_dict(),
        "latest_total_usage": latest_total.to_dict() if latest_total else None,
        "effective_usage": effective_usage.to_dict(),
        "first_event_ts": first_event_ts.isoformat() if first_event_ts else None,
        "last_event_ts": last_event_ts.isoformat() if last_event_ts else None,
        "first_token_count_ts": first_token_count_ts.isoformat() if first_token_count_ts else None,
        "last_token_count_ts": last_token_count_ts.isoformat() if last_token_count_ts else None,
        "latest_token_event_ts": latest_token_event_ts,
        "latest_rate_limits_ts": (
            latest_rate_limits_dt.isoformat()
            if latest_rate_limits_dt
            else latest_rate_limits_ts
        ),
        "latest_rate_limits": latest_rate_limits.to_dict() if latest_rate_limits else None,
    }


def summarize_sessions(codex_home: Path, include_archived: bool, top_n: int) -> dict[str, Any]:
    files = iter_session_files(codex_home, include_archived)
    aggregate_event_sum = TokenUsage()
    aggregate_session_total = TokenUsage()
    session_reports: list[dict[str, Any]] = []
    total_token_events = 0
    parse_failures = 0

    latest_rate_limits: dict[str, Any] | None = None
    latest_rate_limits_ts: datetime | None = None
    date_range_start: datetime | None = None
    date_range_end: datetime | None = None
    token_date_range_start: datetime | None = None
    token_date_range_end: datetime | None = None

    for path in files:
        try:
            report = scan_session_file(path)
        except Exception:
            parse_failures += 1
            continue

        session_reports.append(report)
        total_token_events += int(report["token_event_count"])

        aggregate_event_sum.add(TokenUsage.from_mapping(report["event_sum_usage"]))
        aggregate_session_total.add(TokenUsage.from_mapping(report["effective_usage"]))

        first_event = parse_iso(report.get("first_event_ts"))
        last_event = parse_iso(report.get("last_event_ts"))
        first_token_count = parse_iso(report.get("first_token_count_ts"))
        last_token_count = parse_iso(report.get("last_token_count_ts"))

        if first_event and (date_range_start is None or first_event < date_range_start):
            date_range_start = first_event
        if last_event and (date_range_end is None or last_event > date_range_end):
            date_range_end = last_event
        if first_token_count and (
            token_date_range_start is None or first_token_count < token_date_range_start
        ):
            token_date_range_start = first_token_count
        if last_token_count and (
            token_date_range_end is None or last_token_count > token_date_range_end
        ):
            token_date_range_end = last_token_count

        rl = report.get("latest_rate_limits")
        ts = parse_iso(report.get("latest_rate_limits_ts"))
        if rl and ts and (latest_rate_limits_ts is None or ts > latest_rate_limits_ts):
            latest_rate_limits_ts = ts
            latest_rate_limits = rl

    token_sessions = [
        session for session in session_reports if session["effective_usage"]["total_tokens"] > 0
    ]
    token_sessions.sort(
        key=lambda item: item["effective_usage"]["total_tokens"],
        reverse=True,
    )

    return {
        "files_scanned": len(files),
        "files_failed": parse_failures,
        "sessions_with_tokens": len(token_sessions),
        "total_token_events": total_token_events,
        "date_range_start": date_range_start.isoformat() if date_range_start else None,
        "date_range_end": date_range_end.isoformat() if date_range_end else None,
        "token_date_range_start": (
            token_date_range_start.isoformat() if token_date_range_start else None
        ),
        "token_date_range_end": token_date_range_end.isoformat() if token_date_range_end else None,
        "aggregate_event_sum_usage": aggregate_event_sum.to_dict(),
        "aggregate_session_effective_usage": aggregate_session_total.to_dict(),
        "latest_rate_limits_ts": latest_rate_limits_ts.isoformat() if latest_rate_limits_ts else None,
        "latest_rate_limits": latest_rate_limits,
        "top_sessions_by_tokens": token_sessions[:top_n],
    }


def summarize_state_db(codex_home: Path, top_threads: int) -> dict[str, Any]:
    db = codex_home / "state_5.sqlite"
    if not db.exists():
        return {"path": str(db), "exists": False}

    out: dict[str, Any] = {"path": str(db), "exists": True}
    try:
        con = sqlite3.connect(db)
        con.row_factory = sqlite3.Row
    except sqlite3.Error as exc:
        out["error"] = str(exc)
        return out

    with con:
        cur = con.cursor()
        threads_count = cur.execute("SELECT COUNT(*) FROM threads").fetchone()[0]
        tokens_sum = cur.execute(
            "SELECT COALESCE(SUM(tokens_used), 0) FROM threads"
        ).fetchone()[0]
        tokens_max = cur.execute(
            "SELECT COALESCE(MAX(tokens_used), 0) FROM threads"
        ).fetchone()[0]
        created_min = cur.execute("SELECT MIN(created_at) FROM threads").fetchone()[0]
        created_max = cur.execute("SELECT MAX(created_at) FROM threads").fetchone()[0]
        updated_min = cur.execute("SELECT MIN(updated_at) FROM threads").fetchone()[0]
        updated_max = cur.execute("SELECT MAX(updated_at) FROM threads").fetchone()[0]

        top_rows = cur.execute(
            """
            SELECT id, created_at, updated_at, model, tokens_used, cwd, title, cli_version
            FROM threads
            ORDER BY tokens_used DESC
            LIMIT ?
            """,
            (top_threads,),
        ).fetchall()

        by_model_rows = cur.execute(
            """
            SELECT COALESCE(model, 'unknown') AS model, COUNT(*) AS thread_count,
                   COALESCE(SUM(tokens_used), 0) AS tokens_used
            FROM threads
            GROUP BY COALESCE(model, 'unknown')
            ORDER BY tokens_used DESC
            """
        ).fetchall()

    con.close()

    out.update(
        {
            "threads_count": int(threads_count),
            "sum_tokens_used": int(tokens_sum),
            "max_tokens_used": int(tokens_max),
            "created_at_min": (
                datetime.fromtimestamp(created_min, tz=UTC).isoformat()
                if created_min is not None
                else None
            ),
            "created_at_max": (
                datetime.fromtimestamp(created_max, tz=UTC).isoformat()
                if created_max is not None
                else None
            ),
            "updated_at_min": (
                datetime.fromtimestamp(updated_min, tz=UTC).isoformat()
                if updated_min is not None
                else None
            ),
            "updated_at_max": (
                datetime.fromtimestamp(updated_max, tz=UTC).isoformat()
                if updated_max is not None
                else None
            ),
            "top_threads": [
                {
                    "id": row["id"],
                    "created_at": datetime.fromtimestamp(row["created_at"], tz=UTC).isoformat()
                    if row["created_at"] is not None
                    else None,
                    "updated_at": datetime.fromtimestamp(row["updated_at"], tz=UTC).isoformat()
                    if row["updated_at"] is not None
                    else None,
                    "model": row["model"],
                    "tokens_used": int(row["tokens_used"] or 0),
                    "cwd": row["cwd"],
                    "title": row["title"],
                    "cli_version": row["cli_version"],
                }
                for row in top_rows
            ],
            "tokens_by_model": [
                {
                    "model": row["model"],
                    "thread_count": int(row["thread_count"]),
                    "tokens_used": int(row["tokens_used"]),
                }
                for row in by_model_rows
            ],
        }
    )
    return out


def summarize_logs_db(codex_home: Path) -> dict[str, Any]:
    db = codex_home / "logs_2.sqlite"
    if not db.exists():
        return {"path": str(db), "exists": False}

    out: dict[str, Any] = {"path": str(db), "exists": True}
    try:
        con = sqlite3.connect(db)
        con.row_factory = sqlite3.Row
    except sqlite3.Error as exc:
        out["error"] = str(exc)
        return out

    usage_sum = TokenUsage()
    response_completed_count = 0
    response_models: dict[str, int] = {}
    parse_errors = 0

    with con:
        cur = con.cursor()
        for row in cur.execute(
            """
            SELECT feedback_log_body
            FROM logs
            WHERE feedback_log_body LIKE 'Received message %'
            """
        ):
            body = row["feedback_log_body"]
            if not isinstance(body, str) or not body.startswith("Received message "):
                continue

            try:
                payload = json.loads(body[len("Received message ") :])
            except json.JSONDecodeError:
                parse_errors += 1
                continue

            if payload.get("type") != "response.completed":
                continue

            response_completed_count += 1
            response = payload.get("response") or {}
            usage_sum.add(TokenUsage.from_mapping(response.get("usage")))
            model = response.get("model") or "unknown"
            response_models[model] = response_models.get(model, 0) + 1

        total_logs = cur.execute("SELECT COUNT(*) FROM logs").fetchone()[0]
        ts_min = cur.execute("SELECT MIN(ts) FROM logs").fetchone()[0]
        ts_max = cur.execute("SELECT MAX(ts) FROM logs").fetchone()[0]
        rate_limit_requests = cur.execute(
            "SELECT COUNT(*) FROM logs WHERE feedback_log_body LIKE '%account/rateLimits/read%'"
        ).fetchone()[0]

    con.close()

    out.update(
        {
            "total_log_rows": int(total_logs),
            "ts_min": datetime.fromtimestamp(ts_min, tz=UTC).isoformat() if ts_min is not None else None,
            "ts_max": datetime.fromtimestamp(ts_max, tz=UTC).isoformat() if ts_max is not None else None,
            "response_completed_count": response_completed_count,
            "response_completed_usage_sum": usage_sum.to_dict(),
            "response_completed_by_model": response_models,
            "rate_limits_read_requests": int(rate_limit_requests),
            "parse_errors": parse_errors,
        }
    )
    return out


def text_report(data: dict[str, Any], top_n: int) -> str:
    lines: list[str] = []

    lines.append("=== CODEX LOCAL AUDIT ===")
    lines.append(f"Generated at: {data['generated_at']}")
    lines.append(f"Codex home: {data['codex_home']}")
    lines.append("")

    cfg = data["config"]
    lines.append("[Config]")
    lines.append(f"- config.toml loaded: {cfg.get('loaded')}")
    lines.append(f"- model: {cfg.get('model')}")
    lines.append(f"- reasoning_effort: {cfg.get('model_reasoning_effort')}")
    lines.append(f"- personality: {cfg.get('personality')}")
    lines.append(f"- approval_policy: {cfg.get('approval_policy')}")
    lines.append(f"- sandbox_mode: {cfg.get('sandbox_mode')}")
    lines.append(f"- web_search: {cfg.get('web_search')}")
    lines.append(f"- projects_count: {cfg.get('projects_count')}")
    lines.append("")

    auth = data["auth"]
    lines.append("[Auth summary (sanitized)]")
    lines.append(f"- loaded: {auth.get('loaded', False)}")
    lines.append(f"- account_id: {auth.get('account_id')}")
    lines.append(f"- plan_type (id_token): {auth.get('plan_type_from_id_token')}")
    lines.append(f"- access_token_exp: {auth.get('access_token_exp')}")
    lines.append(f"- id_token_exp: {auth.get('id_token_exp')}")
    lines.append(f"- subscription_active_until: {auth.get('subscription_active_until')}")
    lines.append("")

    wham = data.get("wham_usage")
    if wham:
        lines.append("[Quota]")
        lines.append(f"- email: {wham.get('email')}")
        lines.append(f"- plan: {wham.get('plan_type')}")
        rl = wham.get("rate_limit", {})
        if rl:
            pw = rl.get("primary_window", {})
            if pw:
                lines.append(
                    f"- primary window: used={pw.get('used_percent')}% "
                    f"remaining={100 - pw.get('used_percent', 0)}% "
                    f"window={format_seconds(pw.get('limit_window_seconds'))} "
                    f"reset_after={format_seconds(pw.get('reset_after_seconds'))}"
                )
            sw = rl.get("secondary_window", {})
            if sw:
                lines.append(
                    f"- secondary window: used={sw.get('used_percent')}% "
                    f"remaining={100 - sw.get('used_percent', 0)}% "
                    f"window={format_seconds(sw.get('limit_window_seconds'))} "
                    f"reset_after={format_seconds(sw.get('reset_after_seconds'))}"
                )
        lines.append("")

    sess = data["sessions"]
    lines.append("[Token usage from sessions/*.jsonl]")
    lines.append(f"- files_scanned: {sess['files_scanned']} (failed: {sess['files_failed']})")
    lines.append(f"- sessions_with_tokens: {sess['sessions_with_tokens']}")
    lines.append(f"- total_token_events: {sess['total_token_events']}")
    lines.append(
        f"- date_range_all_events: {sess.get('date_range_start')} -> {sess.get('date_range_end')}"
    )
    lines.append(
        "- date_range_token_count_events: "
        f"{sess.get('token_date_range_start')} -> {sess.get('token_date_range_end')}"
    )

    ev = TokenUsage.from_mapping(sess["aggregate_event_sum_usage"])
    st = TokenUsage.from_mapping(sess["aggregate_session_effective_usage"])
    lines.append(
        "- aggregate_event_sum_usage: "
        f"input={fmt_int(ev.input_tokens)}, cached={fmt_int(ev.cached_input_tokens)}, "
        f"output={fmt_int(ev.output_tokens)}, reasoning={fmt_int(ev.reasoning_output_tokens)}, "
        f"total={fmt_int(ev.total_tokens)}"
    )
    lines.append(
        "- aggregate_session_effective_usage: "
        f"input={fmt_int(st.input_tokens)}, cached={fmt_int(st.cached_input_tokens)}, "
        f"output={fmt_int(st.output_tokens)}, reasoning={fmt_int(st.reasoning_output_tokens)}, "
        f"total={fmt_int(st.total_tokens)}"
    )

    latest_rl = sess.get("latest_rate_limits")
    if latest_rl:
        primary = latest_rl.get("primary") or {}
        secondary = latest_rl.get("secondary") or {}
        lines.append(f"- latest_rate_limits_ts: {sess.get('latest_rate_limits_ts')}")
        lines.append(f"- plan_type: {latest_rl.get('plan_type')}")
        lines.append(
            "- primary window: "
            f"used={fmt_float(primary.get('used_percent'))}% "
            f"remaining={fmt_float(primary.get('remaining_percent'))}% "
            f"window={primary.get('window_minutes')}m "
            f"reset={primary.get('resets_at_iso')}"
        )
        lines.append(
            "- secondary window: "
            f"used={fmt_float(secondary.get('used_percent'))}% "
            f"remaining={fmt_float(secondary.get('remaining_percent'))}% "
            f"window={secondary.get('window_minutes')}m "
            f"reset={secondary.get('resets_at_iso')}"
        )
        lines.append(f"- credits: {json.dumps(latest_rl.get('credits'), ensure_ascii=False)}")
    else:
        lines.append("- latest_rate_limits: n/a")

    lines.append("")
    lines.append(f"[Top {top_n} sessions by tokens]")
    for idx, item in enumerate(sess["top_sessions_by_tokens"], start=1):
        usage = item["effective_usage"]
        lines.append(
            f"{idx}. session={item['session_id']} model={item.get('model')} "
            f"total={fmt_int(usage['total_tokens'])} input={fmt_int(usage['input_tokens'])} "
            f"cached={fmt_int(usage['cached_input_tokens'])} output={fmt_int(usage['output_tokens'])} "
            f"reasoning={fmt_int(usage['reasoning_output_tokens'])}"
        )
        lines.append(f"   file={item['file']}")

    lines.append("")
    state = data["state_db"]
    lines.append("[state_5.sqlite]")
    lines.append(f"- exists: {state.get('exists')}")
    if state.get("exists"):
        lines.append(f"- threads_count: {fmt_int(state.get('threads_count'))}")
        lines.append(f"- sum_tokens_used: {fmt_int(state.get('sum_tokens_used'))}")
        lines.append(f"- max_tokens_used: {fmt_int(state.get('max_tokens_used'))}")
        lines.append(
            f"- created_at_range: {state.get('created_at_min')} -> {state.get('created_at_max')}"
        )
        lines.append(
            f"- updated_at_range: {state.get('updated_at_min')} -> {state.get('updated_at_max')}"
        )
        lines.append(f"- top_threads_count: {len(state.get('top_threads', []))}")

    lines.append("")
    logs = data["logs_db"]
    lines.append("[logs_2.sqlite]")
    lines.append(f"- exists: {logs.get('exists')}")
    if logs.get("exists"):
        usage = TokenUsage.from_mapping(logs.get("response_completed_usage_sum"))
        lines.append(f"- total_log_rows: {fmt_int(logs.get('total_log_rows'))}")
        lines.append(f"- ts_range: {logs.get('ts_min')} -> {logs.get('ts_max')}")
        lines.append(f"- response_completed_count: {fmt_int(logs.get('response_completed_count'))}")
        lines.append(
            "- response_completed_usage_sum: "
            f"input={fmt_int(usage.input_tokens)}, cached={fmt_int(usage.cached_input_tokens)}, "
            f"output={fmt_int(usage.output_tokens)}, reasoning={fmt_int(usage.reasoning_output_tokens)}, "
            f"total={fmt_int(usage.total_tokens)}"
        )
        lines.append(f"- rate_limits_read_requests: {fmt_int(logs.get('rate_limits_read_requests'))}")

    return "\n".join(lines)


def build_report(
    codex_home: Path,
    top_sessions: int,
    top_threads: int,
    include_archived: bool,
    largest_files: int,
) -> dict[str, Any]:
    version = load_json(codex_home / "version.json")
    auth_summary = summarize_auth(codex_home)
    wham_usage = None
    if auth_summary.get("loaded"):
        auth_path = codex_home / "auth.json"
        try:
            auth_data = json.loads(auth_path.read_text(encoding="utf-8", errors="replace"))
            access_token = auth_data.get("tokens", {}).get("access_token")
            if access_token:
                wham_usage = fetch_wham_usage(access_token)
        except Exception:
            pass

    report = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "codex_home": str(codex_home),
        "version": version,
        "config": summarize_config(codex_home),
        "auth": auth_summary,
        "wham_usage": wham_usage,
        "files": summarize_files(codex_home, top_n=largest_files),
        "sessions": summarize_sessions(
            codex_home,
            include_archived=include_archived,
            top_n=top_sessions,
        ),
        "state_db": summarize_state_db(codex_home, top_threads=top_threads),
        "logs_db": summarize_logs_db(codex_home),
    }
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Audit local Codex configuration and usage from ~/.codex "
            "(tokens, local quota percentages, session/state/log databases)."
        )
    )
    parser.add_argument(
        "--codex-home",
        type=Path,
        default=Path.home() / ".codex",
        help="Path to Codex home directory (default: ~/.codex)",
    )
    parser.add_argument(
        "--top-sessions",
        type=int,
        default=15,
        help="Number of top sessions by tokens to include (default: 15)",
    )
    parser.add_argument(
        "--top-threads",
        type=int,
        default=10,
        help="Number of top thread rows from state_5.sqlite (default: 10)",
    )
    parser.add_argument(
        "--largest-files",
        type=int,
        default=20,
        help="Number of largest local files to include (default: 20)",
    )
    parser.add_argument(
        "--no-archived",
        action="store_true",
        help="Exclude ~/.codex/archived_sessions from token aggregation",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON output instead of text",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional output file path (.json recommended with --json)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    codex_home = args.codex_home.expanduser().resolve()
    if not codex_home.exists():
        print(f"Error: {codex_home} does not exist.")
        return 2

    report = build_report(
        codex_home=codex_home,
        top_sessions=max(1, args.top_sessions),
        top_threads=max(1, args.top_threads),
        include_archived=not args.no_archived,
        largest_files=max(1, args.largest_files),
    )

    if args.json:
        rendered = json.dumps(report, indent=2, ensure_ascii=False)
    else:
        rendered = text_report(report, top_n=max(1, args.top_sessions))

    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
