"""Gemini provider implementation."""

import hashlib
import json
import logging
import os
import ssl
import time
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

# Code Assist API constants
CODE_ASSIST_ENDPOINT = "https://cloudcode-pa.googleapis.com"
CODE_ASSIST_API_VERSION = "v1internal"
CODE_ASSIST_METADATA = {
    "ideType": "IDE_UNSPECIFIED",
    "platform": "PLATFORM_UNSPECIFIED",
    "pluginType": "GEMINI",
}
OAUTH_CLIENT_ID = (
    "681255809395-oo8ft2oprdrnp9e3aqf6av3hmdib135j.apps.googleusercontent.com"
)
OAUTH_CLIENT_SECRET = "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"


class GeminiProvider(BaseProvider):
    """Gemini provider implementation."""

    @property
    def provider_id(self) -> str:
        """Return the unique identifier for the provider."""
        return "gemini"

    @property
    def display_name(self) -> str:
        """Return the human-readable name of the provider."""
        return "Gemini"

    @property
    def default_home_path(self) -> str:
        """Return the default home path for the provider."""
        return "~/.gemini"

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
    ) -> Iterable[SessionRecord | TokenUsageRecord]:
        """Perform a full passive scan of local history.

        Args:
            home_path: The path to the Gemini home directory.

        Yields:
            SessionRecord and TokenUsageRecord objects extracted from chat files.
        """
        home = Path(home_path).expanduser()
        project_mapping = self._get_project_mapping(home)

        for path in self._iter_chat_files(home):
            try:
                yield from self._parse_chat_file(path, project_mapping)
            except Exception:
                logger.exception("Failed to parse Gemini chat file: %s", path)

    def scan_incremental(
        self, home_path: str, sync_state: dict[str, Any]
    ) -> Iterable[SessionRecord | TokenUsageRecord]:
        """Perform an incremental passive scan of local history.

        Args:
            home_path: The path to the Gemini home directory.
            sync_state: A dictionary containing high-water marks for files.

        Yields:
            SessionRecord and TokenUsageRecord objects for changed files.
        """
        home = Path(home_path).expanduser()
        project_mapping = self._get_project_mapping(home)

        for path in self._iter_chat_files(home):
            path_str = str(path)
            try:
                stat = path.stat()
                mtime = stat.st_mtime
                size = stat.st_size

                hwm = sync_state.get(path_str)
                if hwm and hwm.get("mtime") == mtime and hwm.get("size") == size:
                    continue

                yield from self._parse_chat_file(path, project_mapping)

                # Update sync state
                sync_state[path_str] = {
                    "mtime": mtime,
                    "size": size,
                    "last_processed_at": datetime.now(UTC).isoformat(),
                }
            except Exception:
                logger.exception("Failed to parse Gemini chat file: %s", path)

    def probe_active(self, home_path: str) -> Iterable[QuotaRecord]:
        """Perform an active quota probe.

        Args:
            home_path: The path to the Gemini home directory.

        Yields:
            QuotaRecord objects representing current quota usage.
        """
        home = Path(home_path).expanduser()
        oauth_path = home / "oauth_creds.json"
        creds = load_json(oauth_path)
        if not isinstance(creds, dict):
            logger.warning(
                "Gemini oauth_creds.json not found or invalid at %s", oauth_path
            )
            return

        try:
            access_token = self._get_oauth_access_token(creds)
            if not access_token:
                logger.warning("Gemini OAuth access token unavailable")
                return

            load_req = {
                "cloudaicompanionProject": None,
                "metadata": CODE_ASSIST_METADATA,
            }
            load_res = self._http_post_json(
                self._code_assist_url("loadCodeAssist"),
                load_req,
                bearer_token=access_token,
            )
            project = load_res.get("cloudaicompanionProject")
            if not isinstance(project, str) or not project:
                logger.warning("Gemini Code Assist project unavailable")
                return

            quota_res = self._http_post_json(
                self._code_assist_url("retrieveUserQuota"),
                {"project": project},
                bearer_token=access_token,
            )
            buckets = quota_res.get("buckets")
            if not isinstance(buckets, list):
                return

            timestamp = datetime.now(UTC)
            for bucket in buckets:
                if not isinstance(bucket, dict):
                    continue

                remaining_fraction = bucket.get("remainingFraction")
                try:
                    remaining_f = (
                        float(remaining_fraction)
                        if remaining_fraction is not None
                        else None
                    )
                except (TypeError, ValueError):
                    remaining_f = None

                model_id = bucket.get("modelId") or "unknown"
                token_type = bucket.get("tokenType") or "unknown"
                quota_name = f"{model_id}:{token_type}"

                resets_at = parse_iso(bucket.get("resetTime"))

                yield QuotaRecord(
                    provider_id=self.provider_id,
                    quota_name=quota_name,
                    timestamp=timestamp,
                    used_percent=None,  # Will be computed by __post_init__
                    remaining_percent=(
                        remaining_f * 100.0 if remaining_f is not None else None
                    ),
                    window_minutes=None,
                    resets_at=resets_at,
                    source="active_probe",
                    raw_data=bucket,
                )

        except Exception:
            logger.exception("Gemini active quota probe failed")

    def _iter_chat_files(self, home: Path) -> list[Path]:
        """Iterate over all Gemini chat files in the given home directory.

        Args:
            home: Path to the Gemini home directory.

        Returns:
            A list of Paths to chat files.
        """
        base = home / "tmp"
        if not base.exists():
            return []

        files: set[Path] = set()
        patterns = [
            "**/chats/session-*.json",
            "**/chats/session-*.jsonl",
            "**/chats/*/*.json",
            "**/chats/*/*.jsonl",
        ]
        for pattern in patterns:
            files.update(base.glob(pattern))
        return sorted(path for path in files if path.is_file())

    def _get_project_mapping(self, home: Path) -> dict[str, str]:
        """Get a mapping of project hashes to project names.

        Args:
            home: Path to the Gemini home directory.

        Returns:
            A dictionary mapping hashes to names.
        """
        path = home / "projects.json"
        data = load_json(path)
        if not isinstance(data, dict):
            return {}
        return data.get("projects") or {}

    def _parse_chat_file(
        self, path: Path, project_mapping: dict[str, str]
    ) -> Iterable[SessionRecord | TokenUsageRecord]:
        """Parse a single chat file.

        Args:
            path: Path to the chat file.
            project_mapping: Mapping of project hashes to names.

        Yields:
            SessionRecord and TokenUsageRecord objects.
        """
        if path.suffix == ".json":
            data = load_json(path)
            if isinstance(data, dict):
                yield from self._parse_json_chat(path, data, project_mapping)
        elif path.suffix == ".jsonl":
            yield from self._parse_jsonl_chat(path, project_mapping)

    def _parse_json_chat(
        self, path: Path, obj: dict[str, Any], project_mapping: dict[str, str]
    ) -> Iterable[SessionRecord | TokenUsageRecord]:
        """Parse a JSON chat file.

        Args:
            path: Path to the chat file.
            obj: Loaded JSON object.
            project_mapping: Mapping of project hashes to names.

        Yields:
            SessionRecord and TokenUsageRecord objects.
        """
        session_id = obj.get("sessionId") or path.stem
        kind = obj.get("kind")
        project_hash = obj.get("projectHash")
        start_time = parse_iso(obj.get("startTime"))
        last_updated = parse_iso(obj.get("lastUpdated"))
        messages = obj.get("messages") or []

        yield from self._parse_messages_common(
            path=path,
            session_id=session_id,
            kind=kind,
            project_hash=project_hash,
            start_time=start_time,
            last_updated=last_updated,
            messages=messages if isinstance(messages, list) else [],
            project_mapping=project_mapping,
        )

    def _parse_jsonl_chat(
        self, path: Path, project_mapping: dict[str, str]
    ) -> Iterable[SessionRecord | TokenUsageRecord]:
        """Parse a JSONL chat file.

        Args:
            path: Path to the chat file.
            project_mapping: Mapping of project hashes to names.

        Yields:
            SessionRecord and TokenUsageRecord objects.
        """
        session_id = None
        kind = None
        project_hash = None
        start_time: datetime | None = None
        last_updated: datetime | None = None
        messages: list[dict[str, Any]] = []

        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if not isinstance(rec, dict):
                    continue

                # Metadata record
                if rec.get("sessionId") and rec.get("startTime"):
                    session_id = rec.get("sessionId")
                    kind = rec.get("kind")
                    project_hash = rec.get("projectHash")
                    st = parse_iso(rec.get("startTime"))
                    lu = parse_iso(rec.get("lastUpdated"))
                    if st is not None and (start_time is None or st < start_time):
                        start_time = st
                    if lu is not None and (last_updated is None or lu > last_updated):
                        last_updated = lu
                    continue

                # Incremental update
                if "$set" in rec and isinstance(rec["$set"], dict):
                    lu = parse_iso(rec["$set"].get("lastUpdated"))
                    if lu is not None and (last_updated is None or lu > last_updated):
                        last_updated = lu
                    continue

                if rec.get("type"):
                    messages.append(rec)

        yield from self._parse_messages_common(
            path=path,
            session_id=session_id or path.stem,
            kind=kind,
            project_hash=project_hash,
            start_time=start_time,
            last_updated=last_updated,
            messages=messages,
            project_mapping=project_mapping,
        )

    def _parse_messages_common(
        self,
        *,
        path: Path,
        session_id: str,
        kind: str | None,
        project_hash: str | None,
        start_time: datetime | None,
        last_updated: datetime | None,
        messages: list[dict[str, Any]],
        project_mapping: dict[str, str],
    ) -> Iterable[SessionRecord | TokenUsageRecord]:
        """Common message parsing logic for JSON and JSONL.

        Args:
            path: Path to the chat file.
            session_id: External session ID.
            kind: Session kind.
            project_hash: Project hash.
            start_time: Session start time.
            last_updated: Session last updated time.
            messages: List of message objects.
            project_mapping: Mapping of project hashes to names.

        Yields:
            SessionRecord and TokenUsageRecord objects.
        """
        token_records: list[TokenUsageRecord] = []
        models: set[str] = set()

        # Track first/last seen from messages if not in metadata
        first_msg_ts: datetime | None = None
        last_msg_ts: datetime | None = None

        token_message_ids: set[str] = set()

        for message in messages:
            if not isinstance(message, dict):
                continue

            ts = parse_iso(message.get("timestamp"))
            if ts is not None:
                if first_msg_ts is None or ts < first_msg_ts:
                    first_msg_ts = ts
                if last_msg_ts is None or ts > last_msg_ts:
                    last_msg_ts = ts

            if message.get("type") != "gemini":
                continue

            model = message.get("model") or "unknown"
            models.add(model)

            usage_map = message.get("tokens")
            if not isinstance(usage_map, dict):
                continue

            identity = self._token_msg_identity(message)
            if identity in token_message_ids:
                continue
            token_message_ids.add(identity)

            token_records.append(
                TokenUsageRecord(
                    provider_id=self.provider_id,
                    external_session_id=session_id,
                    external_event_id=identity,
                    timestamp=ts or last_updated or datetime.now(UTC),
                    model_name=model,
                    input_tokens=int(
                        usage_map.get("input_tokens") or usage_map.get("input") or 0
                    ),
                    output_tokens=int(
                        usage_map.get("output_tokens") or usage_map.get("output") or 0
                    ),
                    cached_tokens=int(
                        usage_map.get("cached_tokens") or usage_map.get("cached") or 0
                    ),
                    thoughts_tokens=int(
                        usage_map.get("thoughts_tokens")
                        or usage_map.get("thoughts")
                        or 0
                    ),
                    tool_tokens=int(
                        usage_map.get("tool_tokens") or usage_map.get("tool") or 0
                    ),
                    total_tokens=int(
                        usage_map.get("total_tokens") or usage_map.get("total") or 0
                    ),
                    raw_data=usage_map,
                )
            )

        project_name = project_mapping.get(project_hash) if project_hash else None

        yield SessionRecord(
            provider_id=self.provider_id,
            external_session_id=session_id,
            model_name=",".join(sorted(models)) if models else "unknown",
            project_name=project_name,
            created_at=start_time or first_msg_ts,
            last_seen_at=last_updated or last_msg_ts,
            metadata={
                "project_hash": project_hash,
                "kind": kind,
                "file_path": str(path),
            },
        )
        yield from token_records

    def _token_msg_identity(self, message: dict[str, Any]) -> str:
        """Create a deterministic identity for a token-bearing message.

        Args:
            message: The message object.

        Returns:
            A SHA256 hash string.
        """
        msg_id = message.get("id")
        if isinstance(msg_id, str) and msg_id.strip():
            return msg_id
        key = "|".join(
            [
                str(message.get("timestamp") or ""),
                str(message.get("type") or ""),
                str(message.get("model") or ""),
                json.dumps(
                    message.get("tokens") or {},
                    sort_keys=True,
                    ensure_ascii=True,
                ),
            ]
        )
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    def _ssl_context(self) -> ssl.SSLContext:
        """Create a SSL context with CA certificates.

        Returns:
            A SSLContext object.
        """
        for env_name in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE"):
            env_path = os.environ.get(env_name)
            if env_path and Path(env_path).exists():
                return ssl.create_default_context(cafile=env_path)
        return ssl.create_default_context()

    def _code_assist_url(self, method: str) -> str:
        """Construct the URL for a Code Assist API method.

        Args:
            method: The API method name.

        Returns:
            The full URL string.
        """
        endpoint = os.environ.get("CODE_ASSIST_ENDPOINT", CODE_ASSIST_ENDPOINT).rstrip(
            "/"
        )
        version = os.environ.get("CODE_ASSIST_API_VERSION", CODE_ASSIST_API_VERSION)
        return f"{endpoint}/{version}:{method}"

    def _http_post_json(
        self,
        url: str,
        body: dict[str, Any],
        *,
        bearer_token: str | None = None,
        timeout_seconds: int = 20,
    ) -> dict[str, Any]:
        """Perform a JSON POST request.

        Args:
            url: The URL to request.
            body: The JSON body.
            bearer_token: Optional Bearer token for Authorization.
            timeout_seconds: Timeout in seconds.

        Returns:
            The parsed JSON response.
        """
        headers = {"Content-Type": "application/json"}
        if bearer_token:
            headers["Authorization"] = f"Bearer {bearer_token}"
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=timeout_seconds,
                context=self._ssl_context(),
            ) as response:
                payload = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            payload = exc.read().decode("utf-8", errors="replace")
            try:
                error_data = json.loads(payload)
            except json.JSONDecodeError:
                error_data = payload[:1000]
            raise RuntimeError(f"HTTP {exc.code}: {error_data}") from exc
        if not payload.strip():
            return {}
        data = json.loads(payload)
        return data if isinstance(data, dict) else {"value": data}

    def _oauth_expired(self, creds: dict[str, Any], skew_seconds: int = 60) -> bool:
        """Check if OAuth credentials are expired.

        Args:
            creds: The credentials dictionary.
            skew_seconds: Time skew tolerance in seconds.

        Returns:
            True if expired, False otherwise.
        """
        expiry_ms = creds.get("expiry_date")
        if not expiry_ms:
            return False
        try:
            return int(expiry_ms) <= int((time.time() + skew_seconds) * 1000)
        except (TypeError, ValueError):
            return False

    def _get_oauth_access_token(
        self, creds: dict[str, Any], timeout_seconds: int = 20
    ) -> str | None:
        """Get or refresh an OAuth access token.

        Args:
            creds: The credentials dictionary.
            timeout_seconds: Timeout in seconds for refresh call.

        Returns:
            The access token or None.
        """
        access_token = creds.get("access_token")
        if (
            isinstance(access_token, str)
            and access_token
            and not self._oauth_expired(creds)
        ):
            return access_token

        refresh_token = creds.get("refresh_token")
        if not isinstance(refresh_token, str) or not refresh_token:
            return access_token if isinstance(access_token, str) else None

        form = urllib.parse.urlencode(
            {
                "client_id": OAUTH_CLIENT_ID,
                "client_secret": OAUTH_CLIENT_SECRET,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            "https://oauth2.googleapis.com/token",
            data=form,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urllib.request.urlopen(
            request, timeout=timeout_seconds, context=self._ssl_context()
        ) as response:
            data = json.loads(response.read().decode("utf-8", errors="replace"))

        refreshed = data.get("access_token")
        if isinstance(refreshed, str) and refreshed:
            # We don't persist it back to file here, just return it for in-memory use
            return refreshed
        return access_token if isinstance(access_token, str) else None
