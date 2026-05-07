#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
import json
import os
import pty
import re
import select
import sqlite3
import ssl
import struct
import subprocess
import termios
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

COPILOT_ENTITLEMENT_URL = "https://github.com/github-copilot/chat/entitlement"
GITHUB_SESSION_COOKIE_NAMES = (
    "user_session",
    "__Host-user_session_same_site",
    "_gh_sess",
    "logged_in",
    "dotcom_user",
)


@dataclass
class CopilotTokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0

    @classmethod
    def from_mapping(cls, value: dict[str, Any] | None) -> "CopilotTokenUsage":
        if not value:
            return cls()
        input_tokens = int(value.get("inputTokens") or value.get("input_tokens") or 0)
        output_tokens = int(value.get("outputTokens") or value.get("output_tokens") or 0)
        cache_read = int(value.get("cacheReadTokens") or value.get("cache_read_tokens") or 0)
        cache_write = int(value.get("cacheWriteTokens") or value.get("cache_write_tokens") or 0)
        reasoning = int(value.get("reasoningTokens") or value.get("reasoning_tokens") or 0)
        total = int(value.get("totalTokens") or value.get("total_tokens") or (input_tokens + output_tokens))
        return cls(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read,
            cache_write_tokens=cache_write,
            reasoning_tokens=reasoning,
            total_tokens=total,
        )

    def add(self, other: "CopilotTokenUsage") -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cache_read_tokens += other.cache_read_tokens
        self.cache_write_tokens += other.cache_write_tokens
        self.reasoning_tokens += other.reasoning_tokens
        self.total_tokens += other.total_tokens

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def fmt_int(value: int | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:,}".replace(",", " ")


def load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
            clean = re.sub(r"(?m)^\s*//.*$", "", raw)
            return json.loads(clean)
        except Exception:
            return None


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


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _build_cookie_header(cookie_map: dict[str, str]) -> str | None:
    if not cookie_map:
        return None
    pieces: list[str] = []
    for name in GITHUB_SESSION_COOKIE_NAMES:
        val = cookie_map.get(name)
        if val:
            pieces.append(f"{name}={val}")
    if not pieces:
        for name in sorted(cookie_map):
            val = cookie_map.get(name)
            if val:
                pieces.append(f"{name}={val}")
    return "; ".join(pieces) if pieces else None


def _parse_cookie_header(raw_cookie_header: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in raw_cookie_header.split(";"):
        item = item.strip()
        if not item or "=" not in item:
            continue
        name, value = item.split("=", 1)
        name = name.strip()
        value = value.strip()
        if name and value:
            out[name] = value
    return out


def _extract_cookie_from_command(command: str) -> str | None:
    # Match: -b 'k=v; ...' / --cookie "k=v; ..."
    cookie_arg = re.search(
        r"(?:^|\s)(?:-b|--cookie)\s+(?:'([^']+)'|\"([^\"]+)\"|([^\s]+))",
        command,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if cookie_arg:
        cookie_raw = next((g for g in cookie_arg.groups() if g), None)
        if cookie_raw:
            cookie_map = _parse_cookie_header(cookie_raw)
            cookie_header = _build_cookie_header(cookie_map)
            if cookie_header:
                return cookie_header

    # Match: -H 'Cookie: ...'
    for match in re.finditer(
        r"(?:^|\s)-H\s+(?:'([^']+)'|\"([^\"]+)\")",
        command,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        header = next((g for g in match.groups() if g), "")
        if not header:
            continue
        if ":" not in header:
            continue
        h_name, h_value = header.split(":", 1)
        if h_name.strip().lower() != "cookie":
            continue
        cookie_map = _parse_cookie_header(h_value)
        cookie_header = _build_cookie_header(cookie_map)
        if cookie_header:
            return cookie_header
    return None


def _read_cookie_from_command_history(copilot_home: Path) -> tuple[str | None, str | None, str | None]:
    path = copilot_home / "command-history-state.json"
    data = load_json(path)
    if not isinstance(data, dict):
        return None, None, None

    history: list[str] = []
    for key in ("commandHistory", "history"):
        candidate = data.get(key)
        if isinstance(candidate, list):
            history.extend(x for x in candidate if isinstance(x, str))

    if not history:
        return None, None, None

    for command in reversed(history):
        if "github-copilot/chat/entitlement" not in command:
            continue
        cookie = _extract_cookie_from_command(command)
        if cookie:
            return cookie, f"auto:command-history:{path}", None
        return None, f"auto:command-history:{path}", "entitlement command found but no cookie could be extracted"
    return None, None, None


def _read_cookie_from_firefox() -> tuple[str | None, str | None, str | None]:
    base = Path.home() / ".mozilla" / "firefox"
    if not base.exists():
        return None, None, None

    now_ts = int(time.time())
    for profile in sorted(path for path in base.iterdir() if path.is_dir()):
        db = profile / "cookies.sqlite"
        if not db.exists():
            continue
        try:
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            rows = con.execute(
                """
                SELECT name, value
                FROM moz_cookies
                WHERE host IN ('github.com', '.github.com')
                  AND name IN ('user_session', '__Host-user_session_same_site', '_gh_sess', 'logged_in', 'dotcom_user')
                  AND expiry > ?
                """,
                (now_ts,),
            ).fetchall()
            con.close()
        except sqlite3.Error:
            continue

        cookie_map: dict[str, str] = {}
        for name, value in rows:
            if isinstance(name, str) and isinstance(value, str) and value:
                cookie_map[name] = value
        cookie_header = _build_cookie_header(cookie_map)
        if cookie_header:
            return cookie_header, f"auto:firefox:{profile.name}", None
    return None, None, None


def _read_cookie_from_chrome_plain() -> tuple[str | None, str | None, str | None]:
    browser_roots = [
        (Path.home() / ".config" / "google-chrome", "google-chrome"),
        (Path.home() / ".config" / "chromium", "chromium"),
    ]
    encrypted_found = False
    now_chrome = int((time.time() + 11644473600) * 1000000)  # unix -> chrome time

    for root, browser_name in browser_roots:
        if not root.exists():
            continue
        for profile_name in ("Default", "Profile 1", "Profile 2", "Profile 3", "Profile 4", "Profile 5"):
            db = root / profile_name / "Cookies"
            if not db.exists():
                continue
            try:
                con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
                rows = con.execute(
                    """
                    SELECT name, value, encrypted_value
                    FROM cookies
                    WHERE host_key IN ('github.com', '.github.com')
                      AND name IN ('user_session', '__Host-user_session_same_site', '_gh_sess', 'logged_in', 'dotcom_user')
                      AND (expires_utc = 0 OR expires_utc > ?)
                    """,
                    (now_chrome,),
                ).fetchall()
                con.close()
            except sqlite3.Error:
                continue

            cookie_map: dict[str, str] = {}
            for name, value, encrypted in rows:
                if isinstance(name, str) and isinstance(value, str) and value:
                    cookie_map[name] = value
                elif isinstance(encrypted, bytes) and encrypted:
                    encrypted_found = True

            cookie_header = _build_cookie_header(cookie_map)
            if cookie_header:
                return cookie_header, f"auto:{browser_name}:{profile_name}", None

    if encrypted_found:
        return None, None, "browser cookies found but encrypted by Chrome/Chromium keyring"
    return None, None, None


def _read_cookie_header(
    github_cookie: str | None,
    github_cookie_file: Path | None,
    copilot_home: Path,
) -> tuple[str | None, str | None, str | None]:
    if github_cookie and github_cookie.strip():
        return github_cookie.strip(), "argument:--github-cookie", None

    if github_cookie_file:
        cookie_file = github_cookie_file.expanduser()
        try:
            raw = cookie_file.read_text(encoding="utf-8", errors="replace").strip()
        except OSError as exc:
            return None, f"file:{cookie_file}", f"unable to read cookie file: {exc}"
        if raw:
            return raw, f"file:{cookie_file}", None
        return None, f"file:{cookie_file}", "cookie file is empty"

    for env_name in ("COPILOT_GITHUB_COOKIE", "GITHUB_COOKIE"):
        env_cookie = os.environ.get(env_name)
        if env_cookie and env_cookie.strip():
            return env_cookie.strip(), f"env:{env_name}", None

    for candidate in (
        Path.home() / ".config" / "quota-tracker" / "github_cookie.txt",
        Path.home() / ".github-copilot-cookie",
    ):
        if not candidate.exists():
            continue
        try:
            raw = candidate.read_text(encoding="utf-8", errors="replace").strip()
        except OSError as exc:
            return None, f"auto:file:{candidate}", f"unable to read auto cookie file: {exc}"
        if raw:
            return raw, f"auto:file:{candidate}", None

    firefox_cookie, firefox_source, firefox_error = _read_cookie_from_firefox()
    if firefox_cookie:
        return firefox_cookie, firefox_source, None

    chrome_cookie, chrome_source, chrome_error = _read_cookie_from_chrome_plain()
    if chrome_cookie:
        return chrome_cookie, chrome_source, None

    history_cookie, history_source, history_error = _read_cookie_from_command_history(copilot_home)
    if history_cookie:
        return history_cookie, history_source, None

    return (
        None,
        None,
        chrome_error
        or history_error
        or firefox_error
        or "GitHub cookie not found automatically. Try logging in on github.com or pass --github-cookie/--github-cookie-file.",
    )


def _http_get_json(
    url: str,
    *,
    headers: dict[str, str],
    timeout_seconds: int,
) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(
            request,
            timeout=timeout_seconds,
            context=_ssl_context(),
        ) as response:
            payload = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            data = payload[:1000]
        raise RuntimeError(f"HTTP {exc.code}: {data}") from exc

    if not payload.strip():
        return {}
    data = json.loads(payload)
    return data if isinstance(data, dict) else {"value": data}


def _summarize_entitlement_quota(payload: dict[str, Any]) -> dict[str, Any]:
    quotas = payload.get("quotas")
    if not isinstance(quotas, dict):
        quotas = {}
    limits = quotas.get("limits")
    if not isinstance(limits, dict):
        limits = {}
    remaining = quotas.get("remaining")
    if not isinstance(remaining, dict):
        remaining = {}

    limit_requests = _as_int(limits.get("premiumInteractions"))
    requests_remaining = _as_int(remaining.get("premiumInteractions"))
    quota_remaining_percent = _as_float(remaining.get("premiumInteractionsPercentage"))
    chat_percentage = _as_float(remaining.get("chatPercentage"))

    requests_used = None
    if limit_requests is not None and requests_remaining is not None:
        requests_used = max(0, limit_requests - requests_remaining)

    quota_used_percent = (
        max(0.0, 100.0 - quota_remaining_percent)
        if quota_remaining_percent is not None
        else None
    )

    if (
        quota_remaining_percent is None
        and limit_requests is not None
        and limit_requests > 0
        and requests_remaining is not None
    ):
        quota_remaining_percent = max(0.0, (requests_remaining / limit_requests) * 100.0)
        quota_used_percent = max(0.0, 100.0 - quota_remaining_percent)

    return {
        "license_type": payload.get("licenseType"),
        "plan": payload.get("plan"),
        "limit_requests": limit_requests,
        "requests_used": requests_used,
        "requests_remaining": requests_remaining,
        "quota_used_percent": quota_used_percent,
        "quota_remaining_percent": quota_remaining_percent,
        "chat_remaining_percent": chat_percentage,
        "reset_date": quotas.get("resetDate"),
        "overages_enabled": quotas.get("overagesEnabled"),
    }


def probe_entitlement_quota(
    timeout_seconds: int,
    github_cookie: str | None,
    cookie_source: str | None,
    cookie_error: str | None,
) -> dict[str, Any]:
    if not github_cookie:
        return {
            "attempted": True,
            "method": "github-chat-entitlement",
            "available": False,
            "cookie_source": cookie_source,
            "error": cookie_error
            or (
                "GitHub cookie not found automatically. Use --github-cookie, "
                "--github-cookie-file, COPILOT_GITHUB_COOKIE or GITHUB_COOKIE."
            ),
        }

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Cookie": github_cookie,
        "Referer": "https://github.com/settings/copilot/features",
        "User-Agent": (
            os.environ.get("COPILOT_QUOTA_USER_AGENT")
            or (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        ),
        "X-Requested-With": "XMLHttpRequest",
    }
    try:
        payload = _http_get_json(
            COPILOT_ENTITLEMENT_URL,
            headers=headers,
            timeout_seconds=timeout_seconds,
        )
        summary = _summarize_entitlement_quota(payload)
        return {
            "attempted": True,
            "method": "github-chat-entitlement",
            "cookie_source": cookie_source,
            "available": summary.get("limit_requests") is not None
            or summary.get("requests_remaining") is not None,
            **summary,
        }
    except Exception as exc:
        return {
            "attempted": True,
            "method": "github-chat-entitlement",
            "cookie_source": cookie_source,
            "available": False,
            "error": str(exc),
        }


def mask_token(token: str | None) -> str | None:
    if not token:
        return None
    if len(token) <= 12:
        return "*" * len(token)
    return f"{token[:8]}...{token[-4:]}"


def _sanitize_command_history_entry(command: str) -> str:
    text = command.replace("\n", " ").replace("\r", " ")
    text = re.sub(r"(?:-b|--cookie)\s+(?:'[^']*'|\"[^\"]*\"|\S+)", "--cookie <redacted>", text)
    text = re.sub(
        r"(authorization\s*:\s*bearer)\s+[^\s'\";]+",
        r"\1 <redacted>",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\bgh[opusr]_[A-Za-z0-9_]+\b", "<redacted-token>", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > 240:
        return f"{text[:240]}…"
    return text


def format_file_info(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False}
    stat = path.stat()
    return {
        "path": str(path),
        "exists": True,
        "size_bytes": stat.st_size,
        "mtime": datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
    }


def summarize_config(copilot_home: Path) -> dict[str, Any]:
    path = copilot_home / "config.json"
    data = load_json(path)
    if not isinstance(data, dict):
        return {"path": str(path), "exists": path.exists(), "loaded": False}

    tokens = data.get("copilotTokens") or {}
    masked_tokens = {k: mask_token(v) for k, v in tokens.items()}

    return {
        "path": str(path),
        "exists": True,
        "loaded": True,
        "first_launch": data.get("firstLaunchAt"),
        "last_login": data.get("lastLoggedInUser"),
        "logged_in_users": data.get("loggedInUsers"),
        "tokens": masked_tokens,
        "trusted_folders_count": len(data.get("trustedFolders") or []),
    }


def summarize_command_history(copilot_home: Path) -> dict[str, Any]:
    path = copilot_home / "command-history-state.json"
    data = load_json(path)
    if not isinstance(data, dict):
        return {"path": str(path), "exists": path.exists(), "loaded": False}

    history = data.get("history")
    if not isinstance(history, list):
        history = data.get("commandHistory")
    if not isinstance(history, list):
        history = []

    sample = [
        _sanitize_command_history_entry(item)
        for item in history[:10]
        if isinstance(item, str)
    ]

    return {
        "path": str(path),
        "exists": True,
        "loaded": True,
        "count": len(history),
        "sample": sample,
    }


def scan_session_file(path: Path) -> dict[str, Any]:
    session_id = None
    start_time: datetime | None = None
    last_updated: datetime | None = None
    initial_model = None
    current_model = None
    tokens_by_model: dict[str, CopilotTokenUsage] = {}
    event_count = 0
    shutdown_found = False
    models_seen: set[str] = set()

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue

            event_count += 1
            rec_type = rec.get("type")
            data = rec.get("data") or {}
            ts = parse_iso(rec.get("timestamp"))

            if ts:
                if start_time is None or ts < start_time:
                    start_time = ts
                if last_updated is None or ts > last_updated:
                    last_updated = ts

            if rec_type == "session.start":
                session_id = data.get("sessionId")
                initial_model = data.get("selectedModel")
                current_model = initial_model
                if current_model:
                    models_seen.add(current_model)
                st = parse_iso(data.get("startTime"))
                if st:
                    start_time = st

            elif rec_type == "session.model_change":
                current_model = data.get("newModel")
                if current_model:
                    models_seen.add(current_model)

            elif rec_type == "assistant.message":
                # Check for model in message if current_model is not set
                msg_model = data.get("model")
                if msg_model:
                    current_model = msg_model
                    models_seen.add(current_model)
                
                # Some events might have intermediate usage info
                usage_data = data.get("usage")
                if usage_data and current_model:
                    usage = CopilotTokenUsage.from_mapping(usage_data)
                    if current_model not in tokens_by_model:
                        tokens_by_model[current_model] = CopilotTokenUsage()
                    # Note: assistant.message usage might be cumulative for the turn
                    # but we'll prioritize session.shutdown for total session usage per model
                    pass

            elif rec_type == "session.shutdown":
                shutdown_found = True
                metrics = data.get("modelMetrics") or {}
                for m_name, m_data in metrics.items():
                    usage_data = m_data.get("usage")
                    if usage_data:
                        usage = CopilotTokenUsage.from_mapping(usage_data)
                        if m_name not in tokens_by_model:
                            tokens_by_model[m_name] = CopilotTokenUsage()
                        # Replace with shutdown metrics as they are authoritative totals
                        tokens_by_model[m_name] = usage
                        models_seen.add(m_name)

    # Calculate aggregate tokens for this session
    agg = CopilotTokenUsage()
    for usage in tokens_by_model.values():
        agg.add(usage)

    return {
        "file": str(path),
        "session_id": session_id or path.parent.name,
        "start_time": start_time.isoformat() if start_time else None,
        "last_updated": last_updated.isoformat() if last_updated else None,
        "model": initial_model,
        "models_seen": sorted(list(models_seen)),
        "event_count": event_count,
        "shutdown_found": shutdown_found,
        "tokens": agg.to_dict(),
        "tokens_by_model": {m: u.to_dict() for m, u in tokens_by_model.items()},
    }


def summarize_sessions(copilot_home: Path, top_n: int) -> dict[str, Any]:
    state_root = copilot_home / "session-state"
    if not state_root.exists():
        return {"exists": False}

    files = list(state_root.glob("**/events.jsonl"))
    reports: list[dict[str, Any]] = []
    agg_tokens = CopilotTokenUsage()
    models_usage: dict[str, CopilotTokenUsage] = {}
    
    date_start: datetime | None = None
    date_end: datetime | None = None

    for path in files:
        try:
            rep = scan_session_file(path)
            reports.append(rep)
            
            agg_tokens.add(CopilotTokenUsage.from_mapping(rep["tokens"]))
            
            for m_name, m_usage_dict in rep.get("tokens_by_model", {}).items():
                if m_name not in models_usage:
                    models_usage[m_name] = CopilotTokenUsage()
                models_usage[m_name].add(CopilotTokenUsage.from_mapping(m_usage_dict))
            
            ds = parse_iso(rep.get("start_time"))
            de = parse_iso(rep.get("last_updated"))
            if ds and (date_start is None or ds < date_start):
                date_start = ds
            if de and (date_end is None or de > date_end):
                date_end = de
                
        except Exception:
            continue

    top_sessions = sorted(reports, key=lambda r: r["tokens"]["total_tokens"], reverse=True)

    return {
        "exists": True,
        "files_scanned": len(files),
        "date_range_start": date_start.isoformat() if date_start else None,
        "date_range_end": date_end.isoformat() if date_end else None,
        "aggregate_tokens": agg_tokens.to_dict(),
        "tokens_by_model": {m: u.to_dict() for m, u in models_usage.items()},
        "top_sessions_by_tokens": top_sessions[:top_n],
    }


def summarize_files(copilot_home: Path, top_n: int) -> dict[str, Any]:
    interesting = [
        copilot_home / "config.json",
        copilot_home / "command-history-state.json",
        copilot_home / "session-state",
        copilot_home / "logs",
    ]
    inventory = [format_file_info(path) for path in interesting]

    largest: list[dict[str, Any]] = []
    for path in copilot_home.rglob("*"):
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


def _strip_ansi(text: str) -> str:
    ansi = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
    text = ansi.sub("", text)
    text = text.replace("\r", "\n")
    text = text.replace("\x07", "")
    return text


def _extract_quota_from_interactive_output(clean_text: str) -> dict[str, Any]:
    # Copilot footer or /usage might show things like "Usage: 45/50 requests" or "90% used"
    # or token counts.
    quota_used_percent = None
    requests_remaining = None
    tokens_used = None

    # Example patterns (hypothetical based on typical CLI tools)
    # Footer might have: "45/50 (90%)" or similar
    percent_match = re.search(r"([0-9]{1,3}(?:\.[0-9]+)?)%\s+used", clean_text, re.IGNORECASE)
    if percent_match:
        quota_used_percent = float(percent_match.group(1))

    # Look for /usage output patterns
    usage_match = re.search(r"remaining\s+requests:\s*([0-9]+)", clean_text, re.IGNORECASE)
    if usage_match:
        requests_remaining = int(usage_match.group(1))

    # Generic search for /XX
    slash_match = re.search(r"([0-9]+)/([0-9]+)\s+requests", clean_text, re.IGNORECASE)
    if slash_match:
        used = int(slash_match.group(1))
        total = int(slash_match.group(2))
        if total > 0:
            quota_used_percent = (used / total) * 100
            requests_remaining = total - used

    return {
        "quota_used_percent": quota_used_percent,
        "quota_remaining_percent": (
            max(0.0, 100.0 - quota_used_percent) if quota_used_percent is not None else None
        ),
        "requests_remaining": requests_remaining,
    }


def probe_interactive_quota(timeout_seconds: int) -> dict[str, Any]:
    """
    Try to fetch live quota from Copilot CLI interactive footer and /usage command.
    """
    cmd = ["copilot"]
    master_fd = None
    process = None
    raw_chunks: list[bytes] = []
    sent_usage = False
    sent_exit = False

    try:
        master_fd, slave_fd = pty.openpty()

        # Set terminal size to 24x80
        buf = struct.pack("HHHH", 24, 80, 0, 0)
        fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, buf)

        process = subprocess.Popen(
            cmd,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            close_fds=True,
            env={**os.environ, "TERM": "xterm-256color"},
        )
        os.close(slave_fd)

        start = time.monotonic()
        while (time.monotonic() - start) < timeout_seconds:
            if process.poll() is not None:
                break

            ready, _, _ = select.select([master_fd], [], [], 0.2)
            if ready:
                try:
                    chunk = os.read(master_fd, 8192)
                except OSError:
                    break
                if not chunk:
                    break
                raw_chunks.append(chunk)
                text = _strip_ansi(b"".join(raw_chunks).decode("utf-8", errors="replace"))

                # Wait for prompt: "Ask a question", "Ready", etc.
                if not sent_usage and any(p in text for p in ["Ask a question", "Ready", "Type your message"]):
                    os.write(master_fd, b"/usage\n")
                    sent_usage = True

                # Wait for usage output before exiting
                if sent_usage and not sent_exit and any(p in text[text.find("/usage"):] for p in ["Usage", "Requests", "Token"]):
                    os.write(master_fd, b"/exit\n")
                    sent_exit = True

            elapsed = time.monotonic() - start
            if not sent_usage and elapsed > timeout_seconds * 0.7:
                os.write(master_fd, b"/usage\n")
                sent_usage = True
            
            if sent_usage and not sent_exit and elapsed > timeout_seconds * 0.9:
                os.write(master_fd, b"/exit\n")
                sent_exit = True

        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()

        output_text = _strip_ansi(b"".join(raw_chunks).decode("utf-8", errors="replace"))
        parsed = _extract_quota_from_interactive_output(output_text)
        return {
            "attempted": True,
            "method": "interactive-slash-usage",
            "available": parsed["quota_used_percent"] is not None or parsed["requests_remaining"] is not None,
            "return_code": process.returncode if process else None,
            "sent_usage_command": sent_usage,
            "sent_exit_command": sent_exit,
            **parsed,
            "output_excerpt": output_text.strip()[-2000:],
        }
    except FileNotFoundError:
        return {
            "attempted": True,
            "method": "interactive-slash-usage",
            "available": False,
            "error": "copilot command not found",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "attempted": True,
            "method": "interactive-slash-usage",
            "available": False,
            "error": str(exc),
        }
    finally:
        if master_fd is not None:
            try:
                os.close(master_fd)
            except OSError:
                pass


def probe_live_quota(
    timeout_seconds: int,
    github_cookie: str | None,
    cookie_source: str | None,
    cookie_error: str | None,
) -> dict[str, Any]:
    entitlement_probe = probe_entitlement_quota(
        timeout_seconds=timeout_seconds,
        github_cookie=github_cookie,
        cookie_source=cookie_source,
        cookie_error=cookie_error,
    )
    if entitlement_probe.get("available"):
        return entitlement_probe

    interactive_probe = probe_interactive_quota(timeout_seconds=timeout_seconds)
    if interactive_probe.get("available"):
        interactive_probe["fallback_from"] = "github-chat-entitlement"
        if entitlement_probe.get("error"):
            interactive_probe["entitlement_error"] = entitlement_probe.get("error")
        return interactive_probe

    return {
        "attempted": True,
        "method": "github-chat-entitlement+interactive-slash-usage",
        "available": False,
        "error": entitlement_probe.get("error") or interactive_probe.get("error"),
        "entitlement_probe": entitlement_probe,
        "interactive_probe": interactive_probe,
    }


def build_report(
    copilot_home: Path,
    top_sessions: int,
    largest_files: int,
    quota_timeout: int,
    github_cookie: str | None,
    github_cookie_file: Path | None,
) -> dict[str, Any]:
    cookie_value, cookie_source, cookie_error = _read_cookie_header(
        github_cookie=github_cookie,
        github_cookie_file=github_cookie_file,
        copilot_home=copilot_home,
    )
    return {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "copilot_home": str(copilot_home),
        "config": summarize_config(copilot_home),
        "command_history": summarize_command_history(copilot_home),
        "sessions": summarize_sessions(copilot_home, top_n=top_sessions),
        "files": summarize_files(copilot_home, top_n=largest_files),
        "live_quota_probe": probe_live_quota(
            timeout_seconds=quota_timeout,
            github_cookie=cookie_value,
            cookie_source=cookie_source,
            cookie_error=cookie_error,
        ),
    }


def text_report(data: dict[str, Any], top_n: int) -> str:
    lines: list[str] = []
    lines.append("=== COPILOT LOCAL AUDIT ===")
    lines.append(f"Generated at: {data['generated_at']}")
    lines.append(f"Copilot home: {data['copilot_home']}")
    lines.append("")

    cfg = data["config"]
    lines.append("[Config]")
    lines.append(f"- loaded: {cfg.get('loaded')}")
    if cfg.get("loaded"):
        lines.append(f"- first_launch: {cfg.get('first_launch')}")
        last_login = cfg.get("last_login") or {}
        lines.append(f"- last_login: {last_login.get('login')} ({last_login.get('host')})")
        lines.append(f"- trusted_folders_count: {cfg.get('trusted_folders_count')}")
        tokens = cfg.get("tokens") or {}
        for user, token in tokens.items():
            lines.append(f"- token ({user}): {token}")
    lines.append("")

    hist = data.get("command_history")
    if hist and hist.get("exists"):
        lines.append("[Command History]")
        lines.append(f"- total commands: {fmt_int(hist.get('count'))}")
        if hist.get("count", 0) > 0:
            lines.append("- sample commands:")
            for cmd in hist.get("sample", []):
                lines.append(f"  > {cmd}")
        lines.append("")

    sess = data["sessions"]
    lines.append("[Sessions usage from ~/.copilot/session-state/**/events.jsonl]")
    if sess.get("exists"):
        lines.append(f"- files_scanned: {sess.get('files_scanned')}")
        lines.append(f"- date_range: {sess.get('date_range_start')} -> {sess.get('date_range_end')}")
        
        usage = CopilotTokenUsage.from_mapping(sess.get("aggregate_tokens"))
        lines.append(
            "- aggregate_tokens: "
            f"input={fmt_int(usage.input_tokens)}, output={fmt_int(usage.output_tokens)}, "
            f"cache_read={fmt_int(usage.cache_read_tokens)}, cache_write={fmt_int(usage.cache_write_tokens)}, "
            f"reasoning={fmt_int(usage.reasoning_tokens)}, total={fmt_int(usage.total_tokens)}"
        )
        
        lines.append("- usage by model:")
        by_model = sess.get("tokens_by_model") or {}
        for m_name, m_usage_dict in sorted(by_model.items()):
            u = CopilotTokenUsage.from_mapping(m_usage_dict)
            lines.append(
                f"  * {m_name:25} -> total={fmt_int(u.total_tokens):>10}, input={fmt_int(u.input_tokens):>10}, "
                f"output={fmt_int(u.output_tokens):>10}, reasoning={fmt_int(u.reasoning_tokens):>10}"
            )
        
        lines.append("")
        lines.append(f"[Top {top_n} sessions by tokens]")
        for idx, s in enumerate(sess.get("top_sessions_by_tokens", []), start=1):
            u = s.get("tokens") or {}
            models = ", ".join(s.get("models_seen", []))
            lines.append(
                f"{idx}. session={s.get('session_id')} models=[{models}] "
                f"total={fmt_int(u.get('total_tokens'))} input={fmt_int(u.get('input_tokens'))} "
                f"output={fmt_int(u.get('output_tokens'))}"
            )
            lines.append(f"   file={s.get('file')}")
    else:
        lines.append("- No session data found.")

    live_probe = data.get("live_quota_probe")
    if isinstance(live_probe, dict):
        lines.append("")
        lines.append("[Live quota]")
        lines.append(f"- attempted: {live_probe.get('attempted')}")
        lines.append(f"- method: {live_probe.get('method')}")
        lines.append(f"- available: {live_probe.get('available')}")
        if live_probe.get("cookie_source") is not None:
            lines.append(f"- cookie_source: {live_probe.get('cookie_source')}")
        if live_probe.get("error") is not None:
            lines.append(f"- error: {live_probe.get('error')}")
        if live_probe.get("plan") is not None:
            lines.append(f"- plan: {live_probe.get('plan')}")
        if live_probe.get("license_type") is not None:
            lines.append(f"- license_type: {live_probe.get('license_type')}")
        lines.append(f"- return_code: {live_probe.get('return_code')}")
        lines.append(f"- limit_requests: {live_probe.get('limit_requests')}")
        lines.append(f"- requests_used: {live_probe.get('requests_used')}")
        lines.append(
            f"- quota_used_percent: {live_probe.get('quota_used_percent')} "
            f"(remaining={live_probe.get('quota_remaining_percent')})"
        )
        lines.append(f"- requests_remaining: {live_probe.get('requests_remaining')}")
        lines.append(f"- chat_remaining_percent: {live_probe.get('chat_remaining_percent')}")
        lines.append(f"- reset_date: {live_probe.get('reset_date')}")
        lines.append(f"- overages_enabled: {live_probe.get('overages_enabled')}")

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit local Copilot CLI data from ~/.copilot"
    )
    parser.add_argument(
        "--copilot-home",
        type=Path,
        default=Path.home() / ".copilot",
        help="Path to Copilot home directory (default: ~/.copilot)",
    )
    parser.add_argument(
        "--top-sessions",
        type=int,
        default=15,
        help="Number of top sessions to include (default: 15)",
    )
    parser.add_argument(
        "--largest-files",
        type=int,
        default=20,
        help="Number of largest files to include (default: 20)",
    )
    parser.add_argument("--json", action="store_true", help="Render JSON output")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional output file path",
    )
    parser.add_argument(
        "--quota-timeout",
        type=int,
        default=20,
        help="Timeout in seconds for live quota probes (default: 20)",
    )
    parser.add_argument(
        "--github-cookie",
        type=str,
        default=None,
        help=(
            "GitHub Cookie header value for the entitlement endpoint "
            "('name=value; name2=value2')."
        ),
    )
    parser.add_argument(
        "--github-cookie-file",
        type=Path,
        default=None,
        help=(
            "Path to a text file containing the GitHub Cookie header value. "
            "Used when --github-cookie is not provided."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    copilot_home = args.copilot_home.expanduser().resolve()
    if not copilot_home.exists():
        print(f"Error: {copilot_home} does not exist.")
        return 2

    report = build_report(
        copilot_home=copilot_home,
        top_sessions=max(1, args.top_sessions),
        largest_files=max(1, args.largest_files),
        quota_timeout=max(5, args.quota_timeout),
        github_cookie=args.github_cookie,
        github_cookie_file=args.github_cookie_file,
    )

    rendered = (
        json.dumps(report, indent=2, ensure_ascii=False)
        if args.json
        else text_report(report, top_n=max(1, args.top_sessions))
    )

    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
