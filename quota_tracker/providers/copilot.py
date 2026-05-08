"""Copilot provider implementation."""

import hashlib
import json
import logging
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from quota_tracker.core.models import QuotaRecord, SessionRecord, TokenUsageRecord
from quota_tracker.providers.base import BaseProvider
from quota_tracker.utils.helpers import load_json, parse_iso

logger = logging.getLogger(__name__)

COPILOT_ENTITLEMENT_URL = "https://github.com/github-copilot/chat/entitlement"
COPILOT_GITHUB_USER_URL = "https://api.github.com/copilot_internal/user"
COPILOT_DEFAULT_API_URL = "https://api.githubcopilot.com"
COPILOT_WEEKLY_PROBE_MODEL = "claude-haiku-4.5"
COPILOT_INTEGRATION_ID = "copilot-developer-cli"
COPILOT_API_VERSION = "2026-01-09"


class CopilotProvider(BaseProvider):
    """Copilot provider implementation."""

    @property
    def provider_id(self) -> str:
        """Return the unique identifier for the provider."""
        return "copilot"

    @property
    def display_name(self) -> str:
        """Return the human-readable name of the provider."""
        return "Copilot"

    @property
    def default_home_path(self) -> str:
        """Return the default home path for the provider."""
        return "~/.copilot"

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
            home_path: The path to the Copilot home directory.

        Yields:
            SessionRecord and TokenUsageRecord objects extracted from event files.
        """
        home = Path(home_path).expanduser()

        for path in self._iter_event_files(home):
            try:
                yield from self._parse_session_file(path)
            except Exception:
                logger.exception("Failed to parse Copilot event file: %s", path)

    def scan_incremental(
        self, home_path: str, sync_state: dict[str, Any]
    ) -> Iterable[SessionRecord | TokenUsageRecord | QuotaRecord]:
        """Perform an incremental passive scan of local history.

        Args:
            home_path: The path to the Copilot home directory.
            sync_state: A dictionary containing high-water marks for files.

        Yields:
            SessionRecord and TokenUsageRecord objects for changed files.
        """
        home = Path(home_path).expanduser()

        for path in self._iter_event_files(home):
            path_str = str(path)
            try:
                stat = path.stat()
                mtime = stat.st_mtime
                size = stat.st_size

                hwm = sync_state.get(path_str)
                if hwm and hwm.get("mtime") == mtime and hwm.get("size") == size:
                    continue

                yield from self._parse_session_file(path)

                # Update sync state
                sync_state[path_str] = {
                    "mtime": mtime,
                    "size": size,
                    "last_processed_at": datetime.now(UTC).isoformat(),
                }
            except Exception:
                logger.exception("Failed to parse Copilot event file: %s", path)

    def probe_active(self, home_path: str) -> Iterable[QuotaRecord]:
        """Perform an active quota probe.

        Args:
            home_path: The path to the Copilot home directory.

        Yields:
            QuotaRecord objects representing current quota usage.
        """
        home = Path(home_path).expanduser()

        # 1. Weekly probe via API headers
        try:
            yield from self._probe_weekly(home)
        except Exception:
            logger.exception("Copilot weekly quota probe failed")

        # 2. Monthly entitlement probe
        try:
            yield from self._probe_monthly(home)
        except Exception:
            logger.exception("Copilot monthly entitlement probe failed")

    def _iter_event_files(self, home: Path) -> list[Path]:
        """Iterate over all Copilot events.jsonl files."""
        base = home / "session-state"
        if not base.exists():
            return []
        return sorted(base.glob("**/events.jsonl"))

    def _parse_session_file(
        self, path: Path
    ) -> Iterable[SessionRecord | TokenUsageRecord | QuotaRecord]:
        """Parse a single events.jsonl file."""
        session_id = None
        start_time: datetime | None = None
        last_updated: datetime | None = None
        initial_model = "unknown"
        models_seen: set[str] = set()

        token_records: list[TokenUsageRecord] = []
        # We'll collect shutdown metrics separately to prioritize them
        shutdown_token_records: list[TokenUsageRecord] = []
        shutdown_found = False

        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue

                rec_type = rec.get("type")
                data = rec.get("data") or {}
                ts = parse_iso(rec.get("timestamp"))

                if ts:
                    if start_time is None or ts < start_time:
                        start_time = ts
                    if last_updated is None or ts > last_updated:
                        last_updated = ts

                if rec_type == "session.start":
                    session_id = data.get("sessionId") or session_id
                    initial_model = data.get("selectedModel") or initial_model
                    if initial_model != "unknown":
                        models_seen.add(initial_model)
                    st = parse_iso(data.get("startTime"))
                    if st:
                        start_time = st

                elif rec_type == "session.model_change":
                    new_model = data.get("newModel")
                    if new_model:
                        models_seen.add(new_model)

                elif rec_type == "assistant.message":
                    msg_model = data.get("model")
                    if msg_model:
                        models_seen.add(msg_model)

                    usage_data = data.get("usage")
                    if usage_data:
                        event_id = self._deterministic_id(
                            f"{path.name}:{rec.get('timestamp')}:{line}"
                        )
                        token_records.append(
                            self._map_token_usage(
                                usage_data,
                                session_id or path.parent.name,
                                event_id,
                                ts or datetime.now(UTC),
                                msg_model or "unknown",
                            )
                        )

                elif rec_type == "session.shutdown":
                    shutdown_found = True
                    metrics = data.get("modelMetrics") or {}
                    for m_name, m_data in metrics.items():
                        usage_data = m_data.get("usage")
                        if usage_data:
                            models_seen.add(m_name)
                            event_id = self._deterministic_id(
                                f"shutdown:{path.name}:{m_name}"
                            )
                            shutdown_token_records.append(
                                self._map_token_usage(
                                    usage_data,
                                    session_id or path.parent.name,
                                    event_id,
                                    ts or datetime.now(UTC),
                                    m_name,
                                )
                            )

        # If shutdown metrics are found, they are authoritative
        final_token_records = (
            shutdown_token_records
            if shutdown_found and shutdown_token_records
            else token_records
        )

        yield SessionRecord(
            provider_id=self.provider_id,
            external_session_id=session_id or path.parent.name,
            model_name=",".join(sorted(models_seen)) if models_seen else initial_model,
            project_path=None,  # Not directly available in events.jsonl
            project_name=None,
            created_at=start_time,
            last_seen_at=last_updated,
            metadata={
                "models_seen": sorted(models_seen),
                "shutdown_found": shutdown_found,
                "file_path": str(path),
            },
        )
        yield from final_token_records

    def _map_token_usage(
        self,
        data: dict[str, Any],
        session_id: str,
        event_id: str,
        timestamp: datetime,
        model_name: str,
    ) -> TokenUsageRecord:
        """Map raw token usage data to TokenUsageRecord."""
        input_tokens = int(data.get("inputTokens") or data.get("input_tokens") or 0)
        output_tokens = int(data.get("outputTokens") or data.get("output_tokens") or 0)
        cached_tokens = int(
            data.get("cacheReadTokens") or data.get("cache_read_tokens") or 0
        )
        reasoning_tokens = int(
            data.get("reasoningTokens") or data.get("reasoning_tokens") or 0
        )
        total_tokens = int(
            data.get("totalTokens")
            or data.get("total_tokens")
            or (input_tokens + output_tokens)
        )

        return TokenUsageRecord(
            provider_id=self.provider_id,
            external_session_id=session_id,
            external_event_id=event_id,
            timestamp=timestamp,
            model_name=model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            reasoning_tokens=reasoning_tokens,
            total_tokens=total_tokens,
            raw_data=data,
        )

    def _probe_weekly(self, home: Path) -> Iterable[QuotaRecord]:
        """Probe weekly quota via chat completions headers."""
        token = self._get_copilot_token(home)
        if not token:
            logger.warning("Copilot token not found in config.json")
            return

        api_url = self._resolve_api_url(token)
        interaction_id = str(uuid.uuid4())

        status, headers, payload = self._http_request_json_with_headers(
            f"{api_url.rstrip('/')}/chat/completions",
            method="POST",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Openai-Intent": "conversation-agent",
                "X-Initiator": "user",
                "X-GitHub-Api-Version": COPILOT_API_VERSION,
                "Copilot-Integration-Id": COPILOT_INTEGRATION_ID,
                "X-Interaction-Id": interaction_id,
                "User-Agent": "GitHubCopilotChat/internal",
            },
            body={
                "model": COPILOT_WEEKLY_PROBE_MODEL,
                "messages": [{"role": "user", "content": "Reply with ok."}],
                "max_tokens": 1,
                "stream": False,
            },
        )

        if status >= 400:
            logger.error(
                "Copilot weekly probe failed with status %d: %s", status, payload
            )
            return

        yield from self._extract_quota_records(headers)

    def _probe_monthly(self, _home: Path) -> Iterable[QuotaRecord]:
        """Probe monthly entitlement quota."""
        # For now, we only support explicit cookie or maybe we skip it if
        # not configured.
        # The prompt says "Implement a separate probe for entitlement".
        # It also says "Keep it separate from the weekly header probe."

        # We need a cookie for this. For now, let's see if we can find it in environment
        # or a safe place.
        # copilot_local_audit.py searches in many places.
        # But ROADMAP.md says "Never persist the local Copilot token" and
        # "Never persist raw cookies".
        # "Use GitHub cookie discovery only when explicitly enabled or already
        # configured safely."

        # Let's check environment variables first.
        cookie = os.environ.get("COPILOT_GITHUB_COOKIE") or os.environ.get(
            "GITHUB_COOKIE"
        )
        if not cookie:
            return

        try:
            status, headers, payload = self._http_request_json_with_headers(
                COPILOT_ENTITLEMENT_URL,
                method="GET",
                headers={
                    "Accept": "application/json",
                    "Cookie": cookie,
                    "Referer": "https://github.com/settings/copilot/features",
                    "X-Requested-With": "XMLHttpRequest",
                },
            )
            if status == 200:
                yield from self._parse_entitlement_payload(payload)
        except Exception:
            logger.exception("Copilot entitlement probe failed")

    def _get_copilot_token(self, home: Path) -> str | None:
        """Read Copilot token from config.json."""
        cfg = load_json(home / "config.json")
        if not isinstance(cfg, dict):
            return None

        tokens = cfg.get("copilotTokens")
        if not isinstance(tokens, dict) or not tokens:
            return None

        # Try last logged in user
        last_user = cfg.get("lastLoggedInUser")
        if isinstance(last_user, dict):
            host = last_user.get("host")
            login = last_user.get("login")
            if host and login:
                key = f"{host}:{login}"
                token = tokens.get(key)
                if isinstance(token, str) and token.strip():
                    return token.strip()

        # Fallback to any token
        for token in tokens.values():
            if isinstance(token, str) and token.strip():
                return token.strip()

        return None

    def _resolve_api_url(self, token: str) -> str:
        """Resolve API base URL via copilot_internal/user."""
        try:
            data = self._http_get_json(
                COPILOT_GITHUB_USER_URL, headers={"Authorization": f"Bearer {token}"}
            )
            endpoints = data.get("endpoints")
            if isinstance(endpoints, dict):
                api_url = endpoints.get("api")
                if isinstance(api_url, str):
                    return api_url
        except Exception:
            logger.warning("Failed to resolve Copilot API URL, using default")
        return COPILOT_DEFAULT_API_URL

    def _extract_quota_records(self, headers: dict[str, str]) -> Iterable[QuotaRecord]:
        """Extract QuotaRecords from response headers."""
        timestamp = datetime.now(UTC)
        for name, value in headers.items():
            lower = name.lower()
            quota_name = None
            if lower.startswith("x-quota-snapshot-"):
                quota_name = lower[len("x-quota-snapshot-") :]
            elif lower.startswith("x-usage-ratelimit-"):
                quota_name = lower[len("x-usage-ratelimit-") :]

            if not quota_name:
                continue

            parsed = self._parse_quota_header(value)
            if parsed:
                yield QuotaRecord(
                    provider_id=self.provider_id,
                    quota_name=quota_name,
                    timestamp=timestamp,
                    used_percent=parsed.get("used_percent"),
                    remaining_percent=parsed.get("remaining_percent"),
                    window_minutes=None,
                    resets_at=parse_iso(parsed.get("reset_date")),
                    source="active_probe",
                    raw_data=parsed,
                )

    def _parse_quota_header(self, value: str) -> dict[str, Any] | None:
        """Parse a quota header value (query-string style)."""
        try:
            params = urllib.parse.parse_qs(value, keep_blank_values=True)

            def first(n: str) -> str | None:
                """Return the first value for a given name."""
                v = params.get(n)
                return v[0] if v else None

            rem = first("rem")
            if rem is None:
                return None

            remaining = float(rem)
            return {
                "remaining_percent": remaining,
                "used_percent": 100.0 - remaining,
                "reset_date": first("rst"),
                "entitlement": first("ent"),
                "overage": first("ov"),
            }
        except Exception:
            return None

    def _parse_entitlement_payload(
        self, payload: dict[str, Any]
    ) -> Iterable[QuotaRecord]:
        """Parse entitlement JSON payload into QuotaRecords."""
        quotas = payload.get("quotas")
        if not isinstance(quotas, dict):
            return

        timestamp = datetime.now(UTC)
        remaining = quotas.get("remaining") or {}

        # Monthly / Premium Interactions
        rem_percent = remaining.get("premiumInteractionsPercentage")
        if rem_percent is not None:
            yield QuotaRecord(
                provider_id=self.provider_id,
                quota_name="premium_interactions",
                timestamp=timestamp,
                used_percent=100.0 - float(rem_percent),
                remaining_percent=float(rem_percent),
                window_minutes=None,
                resets_at=parse_iso(quotas.get("resetDate")),
                source="active_probe",
                raw_data=quotas,
            )

    def _deterministic_id(self, key: str) -> str:
        """Create a deterministic ID."""
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    def _ssl_context(self) -> ssl.SSLContext:
        """Create a SSL context."""
        for env_name in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE"):
            env_path = os.environ.get(env_name)
            if env_path and Path(env_path).exists():
                return ssl.create_default_context(cafile=env_path)
        return ssl.create_default_context()

    def _http_get_json(
        self, url: str, headers: dict[str, str], timeout_seconds: int = 20
    ) -> dict[str, Any]:
        """Perform a JSON GET request."""
        request = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(
            request, timeout=timeout_seconds, context=self._ssl_context()
        ) as response:
            data = json.loads(response.read().decode("utf-8", errors="replace"))
            if isinstance(data, dict):
                return data
            return {"value": data}

    def _http_request_json_with_headers(
        self,
        url: str,
        *,
        method: str,
        headers: dict[str, str],
        timeout_seconds: int = 20,
        body: dict[str, Any] | None = None,
    ) -> tuple[int, dict[str, str], dict[str, Any]]:
        """Perform a JSON request and return status, headers, and body."""
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(
                request, timeout=timeout_seconds, context=self._ssl_context()
            ) as response:
                status = response.status
                resp_headers = {k.lower(): v for k, v in response.headers.items()}
                resp_body = json.loads(
                    response.read().decode("utf-8", errors="replace")
                )
                return status, resp_headers, resp_body
        except urllib.error.HTTPError as exc:
            status = exc.code
            resp_headers = {k.lower(): v for k, v in exc.headers.items()}
            try:
                resp_body = json.loads(exc.read().decode("utf-8", errors="replace"))
            except Exception:
                resp_body = {}
            return status, resp_headers, resp_body
