"""Antigravity CLI provider implementation."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from quota_tracker.db import QuotaRecord
from quota_tracker.providers.base import (
    PassiveSyncResult,
    ProviderMetadata,
    normalize_quota,
    normalize_session,
)
from quota_tracker.providers.gemini import _get_access_token, _project_from_env
from quota_tracker.providers.http import post_json

_CODE_ASSIST_ENDPOINT = "https://daily-cloudcode-pa.googleapis.com"
_CODE_ASSIST_API_VERSION = "v1internal"
_CODE_ASSIST_METADATA: dict[str, str] = {
    "ideType": "IDE_UNSPECIFIED",
    "platform": "PLATFORM_UNSPECIFIED",
    # The Antigravity backend currently accepts the same public enum used by Gemini CLI.
    "pluginType": "GEMINI",
}
_PASSIVE_SCAN_MARK_VERSION = 1
_LOG_TS_RE = re.compile(
    r"^[IWEF](?P<month>\d{2})(?P<day>\d{2}) "
    r"(?P<clock>\d{2}:\d{2}:\d{2}(?:\.\d+)?)"
)
_PROJECT_RE = re.compile(r'project: using project "([^"]+)" \(id=([^)]+)\)')
_WORKSPACE_RE = re.compile(r"Initializing CLI store manager for workspace (.+)$")
_MODEL_RE = re.compile(
    r'(?:Propagating selected model override to backend: label=|Resolving model )"?([^"]+)"?'
)
_CONVERSATION_RE = re.compile(r"Created conversation ([0-9a-fA-F-]+)")
_PRINT_CONVERSATION_RE = re.compile(r"Print mode: conversation=([0-9a-fA-F-]+),")


def _code_assist_url(method: str) -> str:
    """Build a Code Assist API endpoint URL for Antigravity."""

    return f"{_CODE_ASSIST_ENDPOINT.rstrip('/')}/{_CODE_ASSIST_API_VERSION}:{method}"


def _metadata_for_project(project: str | None) -> dict[str, str]:
    """Build Code Assist metadata, including duetProject when project-scoped."""

    metadata = dict(_CODE_ASSIST_METADATA)
    if project:
        metadata["duetProject"] = project
    return metadata


def _retrieve_quota_buckets(
    token: str, project: str, timeout_seconds: int = 20
) -> list[dict[str, Any]]:
    """Call retrieveUserQuota and return normalized Antigravity quota buckets."""

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


def _model_label_to_id(label: str | None) -> str | None:
    """Normalize UI model labels like 'Gemini 3.5 Flash (High)' to a stable id."""

    if not label:
        return None
    base = re.sub(r"\s*\([^)]*\)\s*$", "", label.strip())
    model = re.sub(r"[^a-z0-9.]+", "-", base.lower()).strip("-")
    return model or None


def _file_mtime_iso(path: Path) -> str:
    """Return a file modification timestamp as ISO UTC."""

    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat()


def _millis_to_iso(value: Any) -> str | None:
    """Convert epoch milliseconds to ISO UTC when possible."""

    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=UTC).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def _log_timestamp(line: str, year: int) -> str | None:
    """Parse a glog-style Antigravity timestamp with year inferred from the log file."""

    match = _LOG_TS_RE.search(line)
    if not match:
        return None
    clock = match.group("clock")
    fmt = "%Y %m %d %H:%M:%S.%f" if "." in clock else "%Y %m %d %H:%M:%S"
    raw = f"{year} {match.group('month')} {match.group('day')} {clock}"
    try:
        return datetime.strptime(raw, fmt).replace(tzinfo=UTC).isoformat()
    except ValueError:
        return None


def _expand_workspace(path: str | None) -> str | None:
    """Expand a workspace path logged by Antigravity."""

    if not path:
        return None
    return str(Path(path.strip()).expanduser())


class AntigravityProvider:
    """Antigravity CLI passive sync and active probe."""

    metadata = ProviderMetadata(
        "antigravity", "Antigravity", "~/.gemini/antigravity-cli", True, True
    )

    def __init__(self, home: str, project_id: str | None = None):
        """Initialize provider with the Antigravity CLI data directory."""

        self.home = Path(home).expanduser()
        self.project_id = project_id.strip() if project_id and project_id.strip() else None

    def _gemini_home(self) -> Path:
        """Return the Gemini config directory that stores Antigravity OAuth credentials."""

        candidates = []
        if self.home.name == "antigravity-cli":
            candidates.append(self.home.parent)
        candidates.extend([self.home, Path.home() / ".gemini"])
        seen: set[Path] = set()
        for candidate in candidates:
            resolved = candidate.expanduser()
            if resolved in seen:
                continue
            seen.add(resolved)
            if (resolved / "oauth_creds.json").exists():
                return resolved
        return Path.home() / ".gemini"

    def _load_default_model(self) -> str | None:
        """Read the selected Antigravity model label from settings.json."""

        settings_path = self.home / "settings.json"
        if not settings_path.exists():
            return None
        try:
            raw = json.loads(settings_path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            return None
        if not isinstance(raw, dict):
            return None
        model = raw.get("model")
        return _model_label_to_id(model) if isinstance(model, str) else None

    def _discover_files(self) -> list[Path]:
        """Discover Antigravity files that can contribute session metadata."""

        if not self.home.exists():
            return []
        files: set[Path] = set()
        for path in (
            self.home / "history.jsonl",
            self.home / "cache" / "last_conversations.json",
        ):
            if path.is_file():
                files.add(path)
        for pattern in ("log/*.log", "conversations/*.pb"):
            files.update(p for p in self.home.glob(pattern) if p.is_file())
        return sorted(files)

    @staticmethod
    def _file_mark(path: Path) -> dict[str, Any]:
        stat = path.stat()
        return {
            "path": str(path),
            "size": stat.st_size,
            "mtime": stat.st_mtime,
            "parser_version": _PASSIVE_SCAN_MARK_VERSION,
        }

    @staticmethod
    def _unchanged(path: Path, previous: Any) -> bool:
        if not isinstance(previous, dict):
            return False
        stat = path.stat()
        return (
            previous.get("size") == stat.st_size
            and previous.get("mtime") == stat.st_mtime
            and previous.get("parser_version") == _PASSIVE_SCAN_MARK_VERSION
        )

    def _add_session(
        self,
        drafts: dict[str, dict[str, Any]],
        *,
        conversation_id: str,
        model_name: str | None,
        project_path: str | None,
        created_at: str | None,
        last_seen_at: str | None,
        metadata: dict[str, Any],
    ) -> None:
        """Merge one observed conversation into session draft state."""

        if not conversation_id:
            return
        project_path = _expand_workspace(project_path)
        draft = drafts.setdefault(
            conversation_id,
            {
                "model_name": model_name or "unknown",
                "project_path": project_path,
                "created_at": created_at or last_seen_at,
                "last_seen_at": last_seen_at or created_at,
                "metadata": {"source_files": []},
            },
        )
        if draft["model_name"] == "unknown" and model_name:
            draft["model_name"] = model_name
        if not draft.get("project_path") and project_path:
            draft["project_path"] = project_path
        if created_at and (not draft.get("created_at") or created_at < draft["created_at"]):
            draft["created_at"] = created_at
        if last_seen_at and (not draft.get("last_seen_at") or last_seen_at > draft["last_seen_at"]):
            draft["last_seen_at"] = last_seen_at
        meta = dict(draft.get("metadata", {}))
        sources = set(meta.get("source_files", []))
        if source := metadata.get("source_file"):
            sources.add(str(source))
        meta.update({k: v for k, v in metadata.items() if k != "source_file" and v is not None})
        meta["source_files"] = sorted(sources)
        draft["metadata"] = meta

    def _parse_history(
        self, path: Path, drafts: dict[str, dict[str, Any]], default_model: str | None
    ) -> int:
        failures = 0
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                failures += 1
                continue
            if not isinstance(row, dict):
                continue
            conversation_id = row.get("conversationId")
            if not isinstance(conversation_id, str) or not conversation_id:
                continue
            ts = _millis_to_iso(row.get("timestamp")) or _file_mtime_iso(path)
            workspace = row.get("workspace") if isinstance(row.get("workspace"), str) else None
            self._add_session(
                drafts,
                conversation_id=conversation_id,
                model_name=default_model,
                project_path=workspace,
                created_at=ts,
                last_seen_at=ts,
                metadata={"source": "history", "source_file": str(path)},
            )
        return failures

    def _parse_last_conversations(
        self, path: Path, drafts: dict[str, dict[str, Any]], default_model: str | None
    ) -> int:
        try:
            raw = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except json.JSONDecodeError:
            return 1
        if not isinstance(raw, dict):
            return 1
        ts = _file_mtime_iso(path)
        for workspace, conversation_id in raw.items():
            if not isinstance(workspace, str) or not isinstance(conversation_id, str):
                continue
            self._add_session(
                drafts,
                conversation_id=conversation_id,
                model_name=default_model,
                project_path=workspace,
                created_at=ts,
                last_seen_at=ts,
                metadata={"source": "last_conversations", "source_file": str(path)},
            )
        return 0

    def _parse_log(
        self, path: Path, drafts: dict[str, dict[str, Any]], default_model: str | None
    ) -> int:
        year = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).year
        current_workspace: str | None = None
        current_project_id: str | None = None
        current_model = default_model
        current_label: str | None = None
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            ts = _log_timestamp(line, year) or _file_mtime_iso(path)
            if match := _PROJECT_RE.search(line):
                current_workspace = match.group(1)
                current_project_id = match.group(2)
                continue
            if match := _WORKSPACE_RE.search(line):
                current_workspace = match.group(1)
                continue
            if match := _MODEL_RE.search(line):
                current_label = match.group(1).strip()
                current_model = _model_label_to_id(current_label) or current_model
                continue
            match = _CONVERSATION_RE.search(line) or _PRINT_CONVERSATION_RE.search(line)
            if match:
                conversation_id = match.group(1)
                self._add_session(
                    drafts,
                    conversation_id=conversation_id,
                    model_name=current_model,
                    project_path=current_workspace,
                    created_at=ts,
                    last_seen_at=ts,
                    metadata={
                        "source": "log",
                        "source_file": str(path),
                        "project_id": current_project_id,
                        "model_label": current_label,
                    },
                )
        return 0

    def _parse_conversation_file(
        self, path: Path, drafts: dict[str, dict[str, Any]], default_model: str | None
    ) -> int:
        ts = _file_mtime_iso(path)
        self._add_session(
            drafts,
            conversation_id=path.stem,
            model_name=default_model,
            project_path=None,
            created_at=ts,
            last_seen_at=ts,
            metadata={"source": "conversation_file", "source_file": str(path)},
        )
        return 0

    def _scan(self, high_water_marks: dict[str, Any] | None = None) -> PassiveSyncResult:
        """Run full or incremental passive scan depending on high-water marks."""

        high_water_marks = high_water_marks or {}
        drafts: dict[str, dict[str, Any]] = {}
        marks: dict[str, Any] = {}
        failures = 0
        default_model = self._load_default_model()

        for path in self._discover_files():
            key = str(path)
            mark = self._file_mark(path)
            if self._unchanged(path, high_water_marks.get(key)):
                marks[key] = mark
                continue
            if path.name == "history.jsonl":
                failures += self._parse_history(path, drafts, default_model)
            elif path.name == "last_conversations.json":
                failures += self._parse_last_conversations(path, drafts, default_model)
            elif path.suffix == ".log":
                failures += self._parse_log(path, drafts, default_model)
            elif path.suffix == ".pb":
                failures += self._parse_conversation_file(path, drafts, default_model)
            marks[key] = mark

        sessions = []
        for conversation_id, draft in drafts.items():
            project_path = draft.get("project_path")
            sessions.append(
                normalize_session(
                    provider_id="antigravity",
                    external_session_id=conversation_id,
                    model_name=draft.get("model_name"),
                    project_path=project_path,
                    project_name=Path(project_path).name if project_path else None,
                    created_at=draft.get("created_at"),
                    last_seen_at=draft.get("last_seen_at"),
                    metadata=draft.get("metadata", {}),
                )
            )
        return PassiveSyncResult(sessions, [], [], marks, failures)

    def passive_scan_full(self) -> PassiveSyncResult:
        """Run a full passive scan."""

        return self._scan({})

    def passive_scan_incremental(self, high_water_marks: dict[str, Any]) -> PassiveSyncResult:
        """Run an incremental passive scan from high-water marks."""

        return self._scan(high_water_marks)

    def active_probe(self) -> list[QuotaRecord]:
        """Run active Antigravity quota probe using local Google OAuth credentials."""

        oauth_path = self._gemini_home() / "oauth_creds.json"
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
        return [
            normalize_quota(
                provider_id="antigravity",
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
