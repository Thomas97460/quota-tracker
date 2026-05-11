"""Gemini provider implementation."""

from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
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
from quota_tracker.providers.http import post_json, ssl_context

_CODE_ASSIST_ENDPOINT = "https://cloudcode-pa.googleapis.com"
_CODE_ASSIST_API_VERSION = "v1internal"
_CODE_ASSIST_METADATA: dict[str, str] = {
    "ideType": "IDE_UNSPECIFIED",
    "platform": "PLATFORM_UNSPECIFIED",
    "pluginType": "GEMINI",
}
_OAUTH_CLIENT_ID = "681255809395-oo8ft2oprdrnp9e3aqf6av3hmdib135j.apps.googleusercontent.com"
_OAUTH_CLIENT_SECRET = "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"
_OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
_PASSIVE_SCAN_MARK_VERSION = 2


def _project_from_env() -> str | None:
    """Return the explicit Google Cloud project configured for work accounts."""

    for name in ("GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_PROJECT_ID"):
        value = os.environ.get(name)
        if value and value.strip():
            return value.strip()
    return None


def _metadata_for_project(project: str | None) -> dict[str, str]:
    """Build Code Assist metadata, including duetProject when project-scoped."""

    metadata = dict(_CODE_ASSIST_METADATA)
    if project:
        metadata["duetProject"] = project
    return metadata


def _code_assist_url(method: str) -> str:
    """Build a Code Assist API endpoint URL for the given RPC method name."""
    return f"{_CODE_ASSIST_ENDPOINT.rstrip('/')}/{_CODE_ASSIST_API_VERSION}:{method}"


def _oauth_expired(creds: dict[str, Any], skew_seconds: int = 60) -> bool:
    """Return True if the OAuth access token is expired or about to expire."""
    expiry_ms = creds.get("expiry_date")
    if not expiry_ms:
        return False
    try:
        return int(expiry_ms) <= int((time.time() + skew_seconds) * 1000)
    except (TypeError, ValueError):
        return False


def _get_access_token(creds: dict[str, Any], timeout_seconds: int = 20) -> str | None:
    """Return a valid OAuth access token, refreshing via refresh_token when expired."""
    access = creds.get("access_token")
    if isinstance(access, str) and access and not _oauth_expired(creds):
        return access
    refresh = creds.get("refresh_token")
    if not isinstance(refresh, str) or not refresh:
        return access if isinstance(access, str) else None
    form = urllib.parse.urlencode(
        {
            "client_id": _OAUTH_CLIENT_ID,
            "client_secret": _OAUTH_CLIENT_SECRET,
            "refresh_token": refresh,
            "grant_type": "refresh_token",
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        _OAUTH_TOKEN_URL,
        data=form,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout_seconds, context=ssl_context()) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="replace"))
    refreshed = data.get("access_token")
    return refreshed if isinstance(refreshed, str) else None


def _retrieve_quota_buckets(
    token: str, project: str, timeout_seconds: int = 20
) -> list[dict[str, Any]]:
    """Call retrieveUserQuota and return a normalized list of quota bucket dicts."""
    result = post_json(
        _code_assist_url("retrieveUserQuota"),
        {"project": project},
        bearer_token=token,
        timeout_seconds=timeout_seconds,
    )
    raw = result.get("buckets")
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for bucket in raw:
        if not isinstance(bucket, dict):
            continue
        model_id = bucket.get("modelId")
        token_type = bucket.get("tokenType")
        if not model_id or not token_type:
            continue
        rf = bucket.get("remainingFraction")
        try:
            rf_float = float(rf) if rf is not None else None
        except (TypeError, ValueError):
            rf_float = None
        out.append(
            {
                "model_id": str(model_id),
                "token_type": str(token_type),
                "reset_time": bucket.get("resetTime"),
                "remaining_percent": round(rf_float * 100, 4) if rf_float is not None else None,
                "used_percent": (
                    round((1.0 - rf_float) * 100, 4) if rf_float is not None else None
                ),
            }
        )
    return out


class GeminiProvider:
    """Gemini passive sync and active probe."""

    metadata = ProviderMetadata("gemini", "Gemini", "~/.gemini", True, True)

    def __init__(self, home: str, project_id: str | None = None):
        """Initialize provider with home path."""
        self.home = Path(home).expanduser()
        self.project_id = project_id.strip() if project_id and project_id.strip() else None
        self._project_hash_map: dict[str, str] | None = None

    def _load_project_hash_map(self) -> dict[str, str]:
        """Build a map from projectHash -> absolute project path.

        Observed local shape: projectHash == sha256(path_string).hexdigest().
        We load candidates from both trustedFolders.json and projects.json keys.
        """

        if self._project_hash_map is not None:
            return self._project_hash_map
        out: dict[str, str] = {}

        def add_path(p: str) -> None:
            s = str(p).strip()
            if not s:
                return
            # Preserve exact string used by Gemini (usually absolute paths).
            h = sha256(s.encode("utf-8")).hexdigest()
            out[h] = s

        trusted_path = self.home / "trustedFolders.json"
        if trusted_path.exists():
            try:
                raw = json.loads(trusted_path.read_text(encoding="utf-8", errors="replace"))
                if isinstance(raw, dict):
                    for key in raw.keys():
                        add_path(str(key))
            except Exception:
                pass

        projects_path = self.home / "projects.json"
        if projects_path.exists():
            try:
                raw = json.loads(projects_path.read_text(encoding="utf-8", errors="replace"))
                if isinstance(raw, dict) and isinstance(raw.get("projects"), dict):
                    for key in raw["projects"].keys():
                        add_path(str(key))
            except Exception:
                pass

        self._project_hash_map = out
        return out

    def _discover_chat_files(self) -> list[Path]:
        """Discover supported Gemini chat JSON/JSONL files under home/tmp."""
        base = self.home / "tmp"
        if not base.exists():
            return []
        files: set[Path] = set()
        for pattern in (
            "**/chats/*.json",
            "**/chats/*.jsonl",
            "**/chats/*/*.json",
            "**/chats/*/*.jsonl",
        ):
            files.update(base.glob(pattern))
        return sorted(p for p in files if p.is_file())

    @staticmethod
    def _tok_int(tokens: dict[str, Any], *keys: str) -> int:
        """Return the first non-zero integer value for a set of token field aliases."""
        for k in keys:
            v = tokens.get(k)
            if v is not None:
                try:
                    return int(v)
                except (TypeError, ValueError):
                    pass
        return 0

    def _parse_json_chat(
        self, path: Path, obj: dict[str, Any]
    ) -> tuple[str, str | None, str | None, list[dict[str, Any]], int]:
        """Parse a JSON-format Gemini chat file."""
        sid = obj.get("sessionId") or path.stem
        project_hash = obj.get("projectHash")
        start_time = obj.get("startTime")
        messages = obj.get("messages")
        if not isinstance(messages, list):
            messages = []
        return sid, project_hash, start_time, messages, 0

    def _parse_jsonl_chat(
        self, path: Path
    ) -> tuple[str, str | None, str | None, list[dict[str, Any]], int]:
        """Parse a JSONL-format Gemini chat file."""
        sid = path.stem
        project_hash = None
        start_time = None
        messages: list[dict[str, Any]] = []
        failures = 0
        for line in path.read_text(errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                failures += 1
                continue
            if not isinstance(rec, dict):
                continue
            if rec.get("sessionId") and rec.get("startTime"):
                sid = rec.get("sessionId") or sid
                project_hash = rec.get("projectHash") or project_hash
                start_time = rec.get("startTime") or start_time
                continue
            if "$set" in rec and isinstance(rec["$set"], dict):
                continue
            if rec.get("type"):
                messages.append(rec)
        return sid, project_hash, start_time, messages, failures

    def _scan(self, high_water_marks: dict[str, Any] | None = None) -> PassiveSyncResult:
        """Run full or incremental scan depending on provided high-water marks."""
        high_water_marks = high_water_marks or {}
        project_hash_map = self._load_project_hash_map()
        sessions = []
        usage: list[dict[str, Any]] = []
        failures = 0
        marks: dict[str, Any] = {}
        for path in self._discover_chat_files():
            stat = path.stat()
            key = str(path)
            prev = high_water_marks.get(key)
            file_mark = {
                "path": key,
                "size": stat.st_size,
                "mtime": stat.st_mtime,
                "last_event_ts": None,
                "parser_version": _PASSIVE_SCAN_MARK_VERSION,
            }
            if (
                prev
                and prev.get("size") == stat.st_size
                and prev.get("mtime") == stat.st_mtime
                and prev.get("parser_version") == _PASSIVE_SCAN_MARK_VERSION
            ):
                marks[key] = file_mark
                continue
            if path.suffix == ".jsonl":
                sid, project_hash, start_time, messages, f = self._parse_jsonl_chat(path)
            else:
                try:
                    obj = json.loads(path.read_text(errors="replace"))
                except json.JSONDecodeError:
                    failures += 1
                    marks[key] = file_mark
                    continue
                if not isinstance(obj, dict):
                    failures += 1
                    marks[key] = file_mark
                    continue
                sid, project_hash, start_time, messages, f = self._parse_json_chat(path, obj)
            failures += f
            models: dict[str, int] = {}
            seen_ids: set[str] = set()
            last_ts = start_time
            for message in messages:
                if not isinstance(message, dict):
                    continue
                ts = message.get("timestamp")
                if ts:
                    last_ts = ts
                if message.get("type") != "gemini":
                    continue
                model = message.get("model")
                if isinstance(model, str) and model.strip():
                    models[model] = models.get(model, 0) + 1
                tokens = message.get("tokens") or {}
                input_t = self._tok_int(tokens, "input_tokens", "input")
                output_t = self._tok_int(tokens, "output_tokens", "output")
                cached_t = self._tok_int(tokens, "cached_tokens", "cached")
                thoughts_t = self._tok_int(tokens, "thoughts_tokens", "thoughts")
                total_t = self._tok_int(tokens, "total_tokens", "total")
                if total_t <= 0:
                    continue
                msg_id = message.get("id")
                if isinstance(msg_id, str) and msg_id.strip():
                    identity = msg_id
                else:
                    identity = sha256(
                        "|".join(
                            [
                                str(message.get("timestamp") or ""),
                                str(message.get("type") or ""),
                                str(model or ""),
                                json.dumps(tokens, sort_keys=True, ensure_ascii=True),
                            ]
                        ).encode("utf-8")
                    ).hexdigest()
                if identity in seen_ids:
                    continue
                seen_ids.add(identity)
                eid = sha256((key + identity).encode()).hexdigest()
                usage.append(
                    normalize_token_usage(
                        provider_id="gemini",
                        external_session_id=sid,
                        external_event_id=eid,
                        timestamp=message.get("timestamp") or datetime.now(UTC).isoformat(),
                        model_name=model,
                        input_tokens=input_t,
                        output_tokens=output_t,
                        cached_tokens=cached_t,
                        thoughts_tokens=thoughts_t,
                        total_tokens=total_t,
                        raw_metadata={"kind": "gemini_message"},
                    )
                )
            model_name = max(models, key=lambda m: models[m]) if models else "unknown"
            project_path = project_hash_map.get(project_hash) if project_hash else None
            sessions.append(
                normalize_session(
                    provider_id="gemini",
                    external_session_id=sid,
                    model_name=model_name,
                    project_path=project_path,
                    project_name=Path(project_path).name if project_path else None,
                    created_at=start_time or last_ts,
                    last_seen_at=last_ts,
                    metadata={
                        "project_hash": project_hash,
                        "source_file": key,
                    },
                )
            )
            file_mark["last_event_ts"] = last_ts
            marks[key] = file_mark
        return PassiveSyncResult(sessions, usage, [], marks, failures)

    def passive_scan_full(self) -> PassiveSyncResult:
        """Run full passive scan."""
        return self._scan({})

    def passive_scan_incremental(self, high_water_marks: dict[str, Any]) -> PassiveSyncResult:
        """Run incremental passive scan from high-water marks."""
        return self._scan(high_water_marks)

    def active_probe(self) -> list[QuotaRecord]:
        """Run active Code Assist quota probe using local OAuth credentials."""
        oauth_path = self.home / "oauth_creds.json"
        if not oauth_path.exists():
            return []
        try:
            creds = json.loads(oauth_path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            return []
        if not isinstance(creds, dict):
            return []
        try:
            token = _get_access_token(creds)
            if not token:
                return []
            explicit_project = self.project_id or _project_from_env()
            load_result = post_json(
                _code_assist_url("loadCodeAssist"),
                {
                    "cloudaicompanionProject": explicit_project,
                    "metadata": _metadata_for_project(explicit_project),
                },
                bearer_token=token,
            )
            project = load_result.get("cloudaicompanionProject") or explicit_project
            if not isinstance(project, str) or not project:
                return []
            buckets = _retrieve_quota_buckets(token, project)
        except Exception:
            return []
        now = datetime.now(UTC).isoformat()
        # Emit one row per (model_id, token_type) bucket; frontend rolls up to families.
        return [
            normalize_quota(
                provider_id="gemini",
                quota_name=f"{b['model_id']}/{b['token_type']}",
                timestamp=now,
                source="active_probe",
                raw_metadata={"model_id": b["model_id"], "token_type": b["token_type"]},
                remaining_percent=b.get("remaining_percent"),
                used_percent=b.get("used_percent"),
                resets_at=b.get("reset_time"),
            )
            for b in buckets
        ]
