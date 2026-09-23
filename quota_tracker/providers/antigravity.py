"""Antigravity CLI provider implementation."""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from quota_tracker.db import QuotaRecord
from quota_tracker.providers.base import (
    PassiveSyncResult,
    ProviderMetadata,
    normalize_session,
    normalize_token_usage,
)

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


def _model_label_to_id(label: str | None) -> str | None:
    """Normalize UI model labels like 'Gemini 3.5 Flash (High)' to a stable id."""

    if not label:
        return None
    base = re.sub(r"\s*\([^)]*\)\s*$", "", label.strip())
    model = re.sub(r"[^a-z0-9.]+", "-", base.lower()).strip("-")
    return model or None


def _normalize_model_name(name: str | None) -> str | None:
    """Map observed Antigravity CLI model names or labels to stable config IDs."""

    normalized = _model_label_to_id(name)
    if not normalized:
        return None

    if "claude-fable-5.1" in normalized or "claude-fable-5-1" in normalized:
        return "claude-fable-5.1"
    if "claude-fable-5" in normalized:
        return "claude-fable-5"
    if "claude-mythos-5" in normalized:
        return "claude-mythos-5"
    if "claude-opus-5.5" in normalized or "claude-opus-5-5" in normalized:
        return "claude-opus-5.5"
    if "claude-opus-5" in normalized:
        return "claude-opus-5"
    if (
        "claude-opus-4.6" in normalized
        or "claude-opus-4-6" in normalized
        or "claude-opus-4.-6" in normalized
    ):
        return "claude-opus-4.6"
    if "claude-opus-4.7" in normalized or "claude-opus-4-7" in normalized:
        return "claude-opus-4.7"
    if (
        "claude-opus-4.8" in normalized
        or "claude-opus-4-8" in normalized
        or "claude-opus-4.-8" in normalized
    ):
        return "claude-opus-4.8"
    if "claude-sonnet-5" in normalized:
        return "claude-sonnet-5"
    if "claude-sonnet-4" in normalized:
        return "claude-sonnet-4"
    if "gpt-oss" in normalized:
        return "gpt-oss"
    if "gemini-3.8-flash" in normalized or "gemini-3-8-flash" in normalized:
        return "gemini-3.8-flash"
    if "gemini-3.7-flash" in normalized or "gemini-3-7-flash" in normalized:
        return "gemini-3.7-flash"
    if "gemini-3.6-flash" in normalized or "gemini-3-6-flash" in normalized:
        return "gemini-3.6-flash"
    if "gemini-3.5-flash-lite" in normalized or "gemini-3-5-flash-lite" in normalized:
        return "gemini-3.5-flash-lite"
    if "gemini-3.5-flash" in normalized or "gemini-3-5-flash" in normalized:
        return "gemini-3.5-flash"
    if (
        "gemini-3.1-pro" in normalized
        or "gemini-3-1-pro" in normalized
        or normalized == "gemini-pro-default"
    ):
        return "gemini-3.1-pro"

    return normalized


def _read_varint(data: bytes, pos: int) -> tuple[int, int]:
    """Parse a single protobuf varint from data starting at pos."""

    val = 0
    shift = 0
    while True:
        byte = data[pos]
        val |= (byte & 0x7F) << shift
        pos += 1
        if not (byte & 0x80):
            break
        shift += 7
    return val, pos


def _parse_proto(data: bytes) -> dict[int, Any]:
    """Partially decode a raw protobuf message into field dictionary."""

    pos = 0
    res: dict[int, Any] = {}
    while pos < len(data):
        try:
            val, pos = _read_varint(data, pos)
            wt = val & 7
            fn = val >> 3
            if wt == 0:
                v, pos = _read_varint(data, pos)
                res[fn] = v
            elif wt == 2:
                length, pos = _read_varint(data, pos)
                val_bytes = data[pos : pos + length]
                pos += length
                res[fn] = val_bytes
            elif wt == 1:
                pos += 8
            elif wt == 5:
                pos += 4
            else:
                break
        except Exception:
            break
    return res


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


def _window_to_minutes(window: str | None) -> int | None:
    """Convert Antigravity quota window string like '5h' or 'weekly' to minutes."""

    if not window:
        return None
    w = window.strip().lower()
    if w == "weekly":
        return 7 * 24 * 60
    if w == "daily":
        return 24 * 60
    if w == "monthly":
        return 30 * 24 * 60
    match = re.match(r"^(\d+)\s*h$", w)
    if match:
        return int(match.group(1)) * 60
    match = re.match(r"^(\d+)\s*m$", w)
    if match:
        return int(match.group(1))
    return None


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
        for pattern in ("log/*.log", "conversations/*.pb", "conversations/*.db"):
            files.update(p for p in self.home.glob(pattern) if p.is_file())
        return sorted(files)

    @staticmethod
    def _file_mark(path: Path) -> dict[str, Any]:
        """Compute change tracking mark for an Antigravity file."""

        stat = path.stat()
        return {
            "path": str(path),
            "size": stat.st_size,
            "mtime": stat.st_mtime,
            "parser_version": _PASSIVE_SCAN_MARK_VERSION,
        }

    @staticmethod
    def _unchanged(path: Path, previous: Any) -> bool:
        """Check whether an Antigravity file has changed since previous mark."""

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
        """Parse Antigravity history.jsonl file into session drafts."""

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
        """Parse Antigravity last_conversations.json into session drafts."""

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
        """Parse Antigravity CLI log file into session drafts."""

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
        """Parse Antigravity conversation protobuf file into session drafts."""

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

    def _parse_conversation_db(
        self,
        path: Path,
        drafts: dict[str, dict[str, Any]],
        token_usages: list[dict[str, Any]],
        default_model: str | None,
    ) -> int:
        """Parse Antigravity conversation SQLite database into session drafts and token usage."""

        conversation_id = path.stem
        ts_init = _file_mtime_iso(path)
        self._add_session(
            drafts,
            conversation_id=conversation_id,
            model_name=default_model,
            project_path=None,
            created_at=ts_init,
            last_seen_at=ts_init,
            metadata={"source": "conversation_db", "source_file": str(path)},
        )

        failures = 0
        try:
            uri = f"file:{path}?mode=ro"
            conn = sqlite3.connect(uri, uri=True)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='gen_metadata';"
            )
            if not cursor.fetchone():
                conn.close()
                return 0
            cursor.execute("SELECT idx, data FROM gen_metadata ORDER BY idx ASC;")
            rows = cursor.fetchall()
            conn.close()
        except Exception:
            return 1

        for idx, blob in rows:
            if not isinstance(blob, bytes):
                continue
            try:
                root = _parse_proto(blob)
                ts_iso = None
                if 4 in root and isinstance(root[4], bytes):
                    ts_proto = _parse_proto(root[4])
                    seconds = ts_proto.get(1)
                    if isinstance(seconds, int):
                        ts_iso = datetime.fromtimestamp(seconds, tz=UTC).isoformat()

                if not ts_iso:
                    ts_iso = ts_init

                model_name = default_model
                if 1 in root and isinstance(root[1], bytes):
                    sub = _parse_proto(root[1])
                    model_label = None
                    if 21 in sub and isinstance(sub[21], bytes):
                        try:
                            model_label = sub[21].decode("utf-8", errors="ignore")
                        except Exception:
                            pass

                    model_key = None
                    if 19 in sub and isinstance(sub[19], bytes):
                        try:
                            model_key = sub[19].decode("utf-8", errors="ignore")
                        except Exception:
                            pass

                    candidate_model = model_label or model_key or default_model
                    model_name = _normalize_model_name(candidate_model) or default_model

                    if 4 in sub and isinstance(sub[4], bytes):
                        tok = _parse_proto(sub[4])
                        input_tok = tok.get(9)
                        output_tok = tok.get(10)

                        event_id_bytes = tok.get(11)
                        if isinstance(event_id_bytes, bytes):
                            event_id = event_id_bytes.decode("utf-8", errors="ignore")
                        else:
                            event_id = f"{conversation_id}_{idx}"

                        if isinstance(input_tok, int) or isinstance(output_tok, int):
                            normalized_usage = normalize_token_usage(
                                provider_id="antigravity",
                                external_session_id=conversation_id,
                                external_event_id=event_id,
                                timestamp=ts_iso,
                                model_name=model_name,
                                raw_metadata={"idx": idx},
                                input_tokens=input_tok,
                                output_tokens=output_tok,
                            )
                            token_usages.append(normalized_usage)

                self._add_session(
                    drafts,
                    conversation_id=conversation_id,
                    model_name=model_name,
                    project_path=None,
                    created_at=ts_iso,
                    last_seen_at=ts_iso,
                    metadata={"source": "conversation_db", "source_file": str(path)},
                )
            except Exception:
                failures += 1

        return failures

    def _scan(self, high_water_marks: dict[str, Any] | None = None) -> PassiveSyncResult:
        """Run full or incremental passive scan depending on high-water marks."""

        high_water_marks = high_water_marks or {}
        drafts: dict[str, dict[str, Any]] = {}
        marks: dict[str, Any] = {}
        token_usages: list[dict[str, Any]] = []
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
            elif path.suffix == ".db":
                failures += self._parse_conversation_db(path, drafts, token_usages, default_model)
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
        return PassiveSyncResult(sessions, token_usages, [], marks, failures)

    def passive_scan_full(self) -> PassiveSyncResult:
        """Run a full passive scan."""

        return self._scan({})

    def passive_scan_incremental(self, high_water_marks: dict[str, Any]) -> PassiveSyncResult:
        """Run an incremental passive scan from high-water marks."""

        return self._scan(high_water_marks)

    def _discover_language_server(self) -> tuple[int | None, str | None]:
        """Discover the HTTP port and CSRF token of the running Antigravity Language Server."""

        import glob
        import os

        active_app_dir = (
            Path(os.environ.get("ANTIGRAVITY_APP_DATA_DIR", "~/.gemini/antigravity-cli"))
            .expanduser()
            .resolve()
        )
        is_active_home = self.home.resolve() == active_app_dir

        port: int | None = None
        csrf_token: str | None = (
            os.environ.get("ANTIGRAVITY_CSRF_TOKEN") if is_active_home else None
        )

        # 1. Environment variable for address
        if is_active_home:
            ls_addr = os.environ.get("ANTIGRAVITY_LS_ADDRESS")
            if ls_addr and ":" in ls_addr:
                try:
                    port = int(ls_addr.split(":")[-1])
                except ValueError:
                    pass

        # 2. Check discovery files in daemon/
        daemon_dir = self.home / "daemon"
        if daemon_dir.exists():
            for p in sorted(
                (f for f in daemon_dir.glob("ls_*.json") if f.is_file()),
                key=lambda x: x.stat().st_mtime,
                reverse=True,
            ):
                try:
                    disc = json.loads(p.read_text(encoding="utf-8", errors="replace"))
                    if isinstance(disc, dict):
                        if not port and "httpPort" in disc:
                            port = int(disc["httpPort"])
                        if not csrf_token and "csrfToken" in disc:
                            csrf_token = str(disc["csrfToken"])
                        if port and csrf_token:
                            return port, csrf_token
                except Exception:
                    pass

        # 3. Check /proc/*/environ if port or CSRF token is still missing
        if is_active_home and (not csrf_token or not port):
            try:
                for env_file in glob.glob("/proc/[0-9]*/environ"):
                    try:
                        with open(env_file, "rb") as ef:
                            env_data = ef.read()
                        if (
                            b"ANTIGRAVITY_CSRF_TOKEN=" in env_data
                            or b"ANTIGRAVITY_LS_ADDRESS=" in env_data
                        ):
                            for entry in env_data.split(b"\0"):
                                if not csrf_token and entry.startswith(b"ANTIGRAVITY_CSRF_TOKEN="):
                                    csrf_token = entry.split(b"=", 1)[1].decode("utf-8", "ignore")
                                if not port and entry.startswith(b"ANTIGRAVITY_LS_ADDRESS="):
                                    val = entry.split(b"=", 1)[1].decode("utf-8", "ignore")
                                    if ":" in val:
                                        try:
                                            port = int(val.split(":")[-1])
                                        except ValueError:
                                            pass
                            if csrf_token and port:
                                return port, csrf_token
                    except (OSError, PermissionError):
                        continue
            except Exception:
                pass

        # 4. Check log files if port still missing
        if not port:
            log_dir = self.home / "log"
            if log_dir.exists():
                log_files = sorted(
                    (p for p in log_dir.glob("cli-*.log") if p.is_file()),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )
                for path in log_files:
                    try:
                        content = path.read_text(encoding="utf-8", errors="replace")
                        matches = re.findall(
                            r"Language server listening on random port at (\d+) for HTTP", content
                        )
                        if matches:
                            port = int(matches[-1])
                            break
                    except Exception:
                        continue

        return port, csrf_token

    def active_probe(self) -> list[QuotaRecord]:
        """Run active Antigravity quota probe by calling the local language server daemon."""

        import urllib.request

        from quota_tracker.providers.base import normalize_quota

        port, csrf_token = self._discover_language_server()
        if not port:
            return []

        headers = {"Content-Type": "application/json"}
        if csrf_token:
            headers["x-codeium-csrf-token"] = csrf_token

        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/exa.language_server_pb.LanguageServerService/RetrieveUserQuotaSummary",
                data=b"{}",
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
        except Exception:
            return []

        if not isinstance(data, dict):
            return []

        buckets: list[dict[str, Any]] = []
        resp_obj = data.get("response", {})
        if isinstance(resp_obj, dict):
            groups = resp_obj.get("groups", [])
            if isinstance(groups, list):
                for g in groups:
                    if isinstance(g, dict):
                        g_buckets = g.get("buckets", [])
                        if isinstance(g_buckets, list):
                            for b in g_buckets:
                                if isinstance(b, dict):
                                    b_copy = dict(b)
                                    if "group" not in b_copy and g.get("displayName"):
                                        b_copy["group"] = g["displayName"]
                                    buckets.append(b_copy)
            if not buckets and "buckets" in resp_obj and isinstance(resp_obj["buckets"], list):
                buckets.extend(b for b in resp_obj["buckets"] if isinstance(b, dict))

        if not buckets and "buckets" in data and isinstance(data["buckets"], list):
            buckets.extend(b for b in data["buckets"] if isinstance(b, dict))

        records: list[QuotaRecord] = []
        now = datetime.now(UTC).isoformat()
        for b in buckets:
            bucket_id = b.get("bucketId")
            if not bucket_id or not isinstance(bucket_id, str):
                continue
            try:
                rf_float = float(b.get("remainingFraction", 0))
            except (TypeError, ValueError):
                rf_float = 0.0
            reset_time = b.get("resetTime")
            if not isinstance(reset_time, str):
                reset_time = None

            window = b.get("window")
            window_str = str(window) if window is not None else None

            records.append(
                normalize_quota(
                    provider_id="antigravity",
                    quota_name=bucket_id,
                    timestamp=now,
                    source="active_probe",
                    raw_metadata=b,
                    used_percent=round((1.0 - rf_float) * 100, 4),
                    remaining_percent=round(rf_float * 100, 4),
                    window_minutes=_window_to_minutes(window_str),
                    resets_at=reset_time,
                )
            )

        return records
