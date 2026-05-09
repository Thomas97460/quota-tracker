"""Copilot provider implementation."""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

from quota_tracker.db import QuotaRecord
from quota_tracker.providers.base import (
    PassiveSyncResult,
    ProviderMetadata,
    normalize_quota,
    normalize_session,
    normalize_token_usage,
)
from quota_tracker.providers.http import get_json, request_with_response_headers

TOKEN_FIELD_NAMES = (
    "input_tokens",
    "inputTokens",
    "prompt_tokens",
    "promptTokens",
    "output_tokens",
    "outputTokens",
    "completion_tokens",
    "completionTokens",
    "cached_tokens",
    "cachedTokens",
    "cached_input_tokens",
    "cachedInputTokens",
    "cache_read_tokens",
    "cacheReadTokens",
    "reasoning_tokens",
    "reasoningTokens",
    "reasoning_output_tokens",
    "reasoningOutputTokens",
    "thoughts_tokens",
    "thoughtsTokens",
    "tool_tokens",
    "toolTokens",
    "total_tokens",
    "totalTokens",
    "total",
)

_COPILOT_GITHUB_USER_URL = "https://api.github.com/copilot_internal/user"
_COPILOT_DEFAULT_API_URL = "https://api.githubcopilot.com"
_COPILOT_PROBE_MODEL = "gpt-5-mini"
_COPILOT_INTEGRATION_ID = "copilot-developer-cli"
_COPILOT_API_VERSION = "2026-01-09"


def _copilot_cli_version() -> str:
    """Detect the installed Copilot CLI version from the local cache directory."""
    pkg_root = Path.home() / ".cache" / "copilot" / "pkg" / "linux-x64"
    if pkg_root.exists():
        versions = sorted((p.name for p in pkg_root.iterdir() if p.is_dir()), reverse=True)
        if versions:
            return versions[0]
    return "unknown"


def _copilot_config_token(home: Path) -> str | None:
    """Read the Copilot bearer token from config.json without persisting it."""
    cfg_path = home / "config.json"
    if not cfg_path.exists():
        return None
    try:
        raw = cfg_path.read_text(encoding="utf-8", errors="replace")
        clean = re.sub(r"(?m)^\s*//.*$", "", raw)
        cfg = json.loads(clean)
    except Exception:
        return None
    if not isinstance(cfg, dict):
        return None
    tokens = cfg.get("copilotTokens")
    if not isinstance(tokens, dict) or not tokens:
        return None
    last_user = cfg.get("lastLoggedInUser")
    if isinstance(last_user, dict):
        host = last_user.get("host")
        login = last_user.get("login")
        if isinstance(host, str) and isinstance(login, str):
            token = tokens.get(f"{host}:{login}")
            if isinstance(token, str) and token.strip():
                return token.strip()
    for token in tokens.values():
        if isinstance(token, str) and token.strip():
            return token.strip()
    return None


def _resolve_copilot_api_url(token: str, timeout_seconds: int = 20) -> str:
    """Resolve the Copilot API base URL via the copilot_internal/user endpoint."""
    try:
        user = get_json(
            _COPILOT_GITHUB_USER_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "User-Agent": f"GitHubCopilotChat/{_copilot_cli_version()}",
            },
            timeout_seconds=timeout_seconds,
        )
        endpoints = user.get("endpoints")
        if isinstance(endpoints, dict) and isinstance(endpoints.get("api"), str):
            return str(endpoints["api"])
    except Exception:
        pass
    return _COPILOT_DEFAULT_API_URL


def _parse_quota_header_value(value: str) -> dict[str, Any] | None:
    """Parse a Copilot quota header query string into a normalized dict."""
    try:
        params = parse_qs(value, keep_blank_values=True)

        def first(name: str) -> str | None:
            """Return the first value for a query parameter key."""
            vals = params.get(name)
            return vals[0] if vals else None

        try:
            entitlement = int(first("ent") or "0")
        except (TypeError, ValueError):
            return None
        try:
            overage = float(first("ov") or "0.0")
        except (TypeError, ValueError):
            return None
        try:
            remaining = float(first("rem") or "0.0")
        except (TypeError, ValueError):
            return None

        reset = first("rst") or None
        is_unlimited = entitlement == -1
        used_percent = max(0.0, min(100.0, 100.0 - remaining))
        out: dict[str, Any] = {
            "is_unlimited_entitlement": is_unlimited,
            "entitlement_requests": entitlement,
            "overage": overage,
            "remaining_percent": remaining,
            "used_percent": used_percent,
            "reset_date": reset,
        }
        has_quota = first("hasQuota")
        if has_quota is not None:
            out["has_quota"] = has_quota == "true"
        return out
    except Exception:
        return None


def _extract_quota_headers(headers: dict[str, str]) -> dict[str, dict[str, Any]]:
    """Extract and parse all Copilot quota headers from a response header dict."""
    out: dict[str, dict[str, Any]] = {}
    for name, value in headers.items():
        lower = name.lower()
        if lower.startswith("x-quota-snapshot-"):
            key = lower[len("x-quota-snapshot-") :]
        elif lower.startswith("x-usage-ratelimit-"):
            key = lower[len("x-usage-ratelimit-") :]
        else:
            continue
        parsed = _parse_quota_header_value(value)
        if parsed is not None:
            out[key] = parsed
    return out


class CopilotProvider:
    """Copilot passive sync and active quota probing."""

    metadata = ProviderMetadata("copilot", "Copilot", "~/.copilot", True, True)

    def __init__(self, home: str):
        """Initialize provider options."""
        self.home = Path(home).expanduser()

    def _event_files(self) -> list[Path]:
        """Discover Copilot session event files."""
        return sorted(self.home.glob("session-state/**/events.jsonl"))

    def _scan(self, hwm: dict[str, Any] | None = None) -> PassiveSyncResult:
        """Run full or incremental passive scan."""
        hwm = hwm or {}
        sessions = []
        usage: list[dict[str, Any]] = []
        quotas: list[QuotaRecord] = []
        marks: dict[str, dict[str, Any]] = {}
        failures = 0
        for p in self._event_files():
            st = p.stat()
            key = str(p)
            prev = hwm.get(key)
            mark = {"path": key, "size": st.st_size, "mtime": st.st_mtime, "last_event_ts": None}
            if prev and prev.get("size") == st.st_size and prev.get("mtime") == st.st_mtime:
                marks[key] = mark
                continue
            sid = p.parent.name
            models_seen: set[str] = set()
            current_model: str | None = None
            last_ts = None
            for index, line in enumerate(p.read_text(errors="replace").splitlines()):
                if not line.strip():
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    failures += 1
                    continue
                last_ts = ev.get("timestamp") or last_ts
                m = ev.get("model") or ev.get("modelName")
                if m:
                    current_model = str(m)
                    models_seen.add(current_model)
                for usage_model, payload in self._usage_payloads(ev):
                    timestamp = ev.get("timestamp") or datetime.now(UTC).isoformat()
                    model = str(
                        usage_model
                        or ev.get("model")
                        or ev.get("modelName")
                        or current_model
                        or "unknown"
                    )
                    models_seen.add(model)
                    source_id = ev.get("id") or ev.get("event_id") or ev.get("timestamp") or index
                    eid = sha256(f"{key}:{index}:{source_id}".encode()).hexdigest()
                    usage.append(
                        normalize_token_usage(
                            "copilot",
                            sid,
                            eid,
                            timestamp,
                            model,
                            raw_metadata={
                                "kind": ev.get("type") or ev.get("event"),
                                "source_file": key,
                                "usage_keys": sorted(payload.keys()),
                            },
                            input_tokens=self._first_int(
                                payload,
                                "input_tokens",
                                "inputTokens",
                                "prompt_tokens",
                                "promptTokens",
                            ),
                            output_tokens=self._first_int(
                                payload,
                                "output_tokens",
                                "outputTokens",
                                "completion_tokens",
                                "completionTokens",
                            ),
                            cached_tokens=self._first_int(
                                payload,
                                "cached_tokens",
                                "cachedTokens",
                                "cached_input_tokens",
                                "cachedInputTokens",
                                "cache_read_tokens",
                                "cacheReadTokens",
                            ),
                            reasoning_tokens=self._first_int(
                                payload,
                                "reasoning_tokens",
                                "reasoningTokens",
                                "reasoning_output_tokens",
                                "reasoningOutputTokens",
                            ),
                            thoughts_tokens=self._first_int(
                                payload, "thoughts_tokens", "thoughtsTokens"
                            ),
                            tool_tokens=self._first_int(payload, "tool_tokens", "toolTokens"),
                            total_tokens=self._first_int(
                                payload, "total_tokens", "totalTokens", "total"
                            ),
                            source="local_log",
                        )
                    )
            sessions.append(
                normalize_session(
                    "copilot",
                    sid,
                    next(iter(models_seen), "unknown"),
                    None,
                    None,
                    last_ts,
                    last_ts,
                    {"models_seen": sorted(models_seen)},
                )
            )
            mark["last_event_ts"] = last_ts
            marks[key] = mark
        return PassiveSyncResult(sessions, usage, quotas, marks, failures)

    @staticmethod
    def _usage_payloads(event: dict[str, Any]) -> list[tuple[str | None, dict[str, Any]]]:
        """Extract one or more Copilot token usage payloads from an event."""
        data = event.get("data")
        if isinstance(data, dict) and isinstance(data.get("modelMetrics"), dict):
            payloads: list[tuple[str | None, dict[str, Any]]] = []
            for model_name, model_data in data["modelMetrics"].items():
                usage = model_data.get("usage")
                if isinstance(usage, dict) and any(name in usage for name in TOKEN_FIELD_NAMES):
                    payloads.append((str(model_name), usage))
            if payloads:
                return payloads
        single = CopilotProvider._usage_payload(event)
        return [(None, single)] if single else []

    @staticmethod
    def _usage_payload(event: dict[str, Any]) -> dict[str, Any]:
        """Extract a Copilot token usage payload from known event shapes."""
        for key in ("usage", "usageMetadata", "token_usage", "tokenUsage", "metrics"):
            value = event.get(key)
            if isinstance(value, dict) and any(name in value for name in TOKEN_FIELD_NAMES):
                return value
        if any(name in event for name in TOKEN_FIELD_NAMES):
            return event
        return {}

    @staticmethod
    def _first_int(payload: dict[str, Any], *keys: str) -> int | None:
        """Return the first numeric token count for a list of accepted field names."""
        for key in keys:
            value = payload.get(key)
            if isinstance(value, int | float):
                return int(value)
        return None

    def passive_scan_full(self) -> PassiveSyncResult:
        """Run full passive scan."""
        return self._scan({})

    def passive_scan_incremental(self, high_water_marks: dict[str, Any]) -> PassiveSyncResult:
        """Run incremental passive scan."""
        return self._scan(high_water_marks)

    @staticmethod
    def parse_quota_headers(headers: dict[str, str], timestamp: str) -> list[QuotaRecord]:
        """Parse Copilot quota response headers into normalized quota records."""
        parsed = _extract_quota_headers(headers)
        out: list[QuotaRecord] = []
        for quota_name, data in parsed.items():
            out.append(
                normalize_quota(
                    "copilot",
                    quota_name,
                    timestamp,
                    "active_probe",
                    {k: v for k, v in data.items() if k != "reset_date"},
                    remaining_percent=data.get("remaining_percent"),
                    used_percent=data.get("used_percent"),
                    resets_at=data.get("reset_date"),
                )
            )
        return out

    def active_probe(self) -> list[QuotaRecord]:
        """Run active weekly quota probe via Copilot chat completions API headers."""
        token = _copilot_config_token(self.home)
        if not token:
            return []
        try:
            api_url = _resolve_copilot_api_url(token)
            interaction_id = str(uuid.uuid4())
            cli_version = _copilot_cli_version()
            _, response_headers, _ = request_with_response_headers(
                f"{api_url.rstrip('/')}/chat/completions",
                method="POST",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "Openai-Intent": "conversation-agent",
                    "X-Initiator": "user",
                    "X-GitHub-Api-Version": _COPILOT_API_VERSION,
                    "Copilot-Integration-Id": _COPILOT_INTEGRATION_ID,
                    "X-Interaction-Id": interaction_id,
                    "User-Agent": f"GitHubCopilotChat/{cli_version}",
                },
                body={
                    "model": _COPILOT_PROBE_MODEL,
                    "messages": [{"role": "user", "content": "Reply with ok."}],
                    "max_tokens": 1,
                    "stream": False,
                },
            )
        except Exception:
            return []
        now = datetime.now(UTC).isoformat()
        return self.parse_quota_headers(response_headers, now)
