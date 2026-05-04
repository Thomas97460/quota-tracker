#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import pty
import re
import select
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass
class GeminiTokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    thoughts_tokens: int = 0
    tool_tokens: int = 0
    total_tokens: int = 0

    @classmethod
    def from_mapping(cls, value: dict[str, Any] | None) -> "GeminiTokenUsage":
        if not value:
            return cls()
        return cls(
            input_tokens=int(value.get("input_tokens") or value.get("input") or 0),
            output_tokens=int(value.get("output_tokens") or value.get("output") or 0),
            cached_tokens=int(value.get("cached_tokens") or value.get("cached") or 0),
            thoughts_tokens=int(value.get("thoughts_tokens") or value.get("thoughts") or 0),
            tool_tokens=int(value.get("tool_tokens") or value.get("tool") or 0),
            total_tokens=int(value.get("total_tokens") or value.get("total") or 0),
        )

    def add(self, other: "GeminiTokenUsage") -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cached_tokens += other.cached_tokens
        self.thoughts_tokens += other.thoughts_tokens
        self.tool_tokens += other.tool_tokens
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
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
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


def mask_value(value: str | None, keep: int = 4) -> str | None:
    if not value:
        return None
    if len(value) <= keep * 2:
        return "*" * len(value)
    return f"{value[:keep]}...{value[-keep:]}"


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


def summarize_settings(gemini_home: Path) -> dict[str, Any]:
    path = gemini_home / "settings.json"
    data = load_json(path)
    if not isinstance(data, dict):
        return {"path": str(path), "exists": path.exists(), "loaded": False}
    return {
        "path": str(path),
        "exists": True,
        "loaded": True,
        "session_retention": ((data.get("general") or {}).get("sessionRetention")),
        "ui_footer_items": (((data.get("ui") or {}).get("footer") or {}).get("items")),
        "auth_selected_type": (((data.get("security") or {}).get("auth") or {}).get("selectedType")),
    }


def summarize_projects(gemini_home: Path) -> dict[str, Any]:
    path = gemini_home / "projects.json"
    data = load_json(path)
    if not isinstance(data, dict):
        return {"path": str(path), "exists": path.exists(), "loaded": False}
    projects = data.get("projects") or {}
    return {
        "path": str(path),
        "exists": True,
        "loaded": True,
        "project_count": len(projects),
        "sample_project_names": list(projects.values())[:25],
    }


def summarize_oauth(gemini_home: Path) -> dict[str, Any]:
    path = gemini_home / "oauth_creds.json"
    data = load_json(path)
    if not isinstance(data, dict):
        return {"path": str(path), "exists": path.exists(), "loaded": False}

    id_payload = decode_jwt_payload(data.get("id_token"))
    id_exp = None
    if isinstance(id_payload, dict) and id_payload.get("exp") is not None:
        try:
            id_exp = datetime.fromtimestamp(int(id_payload["exp"]), tz=UTC).isoformat()
        except Exception:
            id_exp = None

    scope_value = data.get("scope") or ""
    if isinstance(scope_value, str):
        scopes = [s for s in scope_value.split() if s.strip()]
    else:
        scopes = []

    return {
        "path": str(path),
        "exists": True,
        "loaded": True,
        "token_presence": {
            "access_token": bool(data.get("access_token")),
            "id_token": bool(data.get("id_token")),
            "refresh_token": bool(data.get("refresh_token")),
        },
        "token_type": data.get("token_type"),
        "expiry_date_raw": data.get("expiry_date"),
        "id_token_exp": id_exp,
        "scope_count": len(scopes),
        "scope_sample": scopes[:10],
    }


def summarize_accounts(gemini_home: Path) -> dict[str, Any]:
    path = gemini_home / "google_accounts.json"
    data = load_json(path)
    if not isinstance(data, dict):
        return {"path": str(path), "exists": path.exists(), "loaded": False}
    active = data.get("active")
    old = data.get("old")
    old_count = len(old) if isinstance(old, list) else None
    return {
        "path": str(path),
        "exists": True,
        "loaded": True,
        "active_account_masked": mask_value(active if isinstance(active, str) else None),
        "old_accounts_count": old_count,
    }


def iter_chat_files(gemini_home: Path) -> list[Path]:
    base = gemini_home / "tmp"
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


def _extract_text_fields(content: Any) -> list[str]:
    out: list[str] = []
    if isinstance(content, str):
        out.append(content)
    elif isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                out.append(item["text"])
            elif isinstance(item, str):
                out.append(item)
    return out


def _token_msg_identity(message: dict[str, Any]) -> str:
    msg_id = message.get("id")
    if isinstance(msg_id, str) and msg_id.strip():
        return msg_id
    key = "|".join(
        [
            str(message.get("timestamp") or ""),
            str(message.get("type") or ""),
            str(message.get("model") or ""),
            json.dumps(message.get("tokens") or {}, sort_keys=True, ensure_ascii=True),
        ]
    )
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _parse_json_chat(path: Path, obj: dict[str, Any]) -> dict[str, Any]:
    session_id = obj.get("sessionId")
    kind = obj.get("kind")
    project_hash = obj.get("projectHash")
    start_time = parse_iso(obj.get("startTime"))
    last_updated = parse_iso(obj.get("lastUpdated"))
    messages = obj.get("messages") or []

    return _parse_messages_common(
        path=path,
        session_id=session_id,
        kind=kind,
        project_hash=project_hash,
        start_time=start_time,
        last_updated=last_updated,
        messages=messages if isinstance(messages, list) else [],
    )


def _parse_jsonl_chat(path: Path) -> dict[str, Any]:
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

            # Metadata record (first line in Gemini chat JSONL files).
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

            # Incremental update of lastUpdated.
            if "$set" in rec and isinstance(rec["$set"], dict):
                lu = parse_iso(rec["$set"].get("lastUpdated"))
                if lu is not None and (last_updated is None or lu > last_updated):
                    last_updated = lu
                continue

            if rec.get("type"):
                messages.append(rec)

    return _parse_messages_common(
        path=path,
        session_id=session_id or path.stem,
        kind=kind,
        project_hash=project_hash,
        start_time=start_time,
        last_updated=last_updated,
        messages=messages,
    )


def _parse_messages_common(
    *,
    path: Path,
    session_id: str | None,
    kind: str | None,
    project_hash: str | None,
    start_time: datetime | None,
    last_updated: datetime | None,
    messages: list[dict[str, Any]],
) -> dict[str, Any]:
    message_count = 0
    gemini_message_count = 0
    tokens = GeminiTokenUsage()
    token_message_ids: set[str] = set()
    models: dict[str, int] = {}
    first_msg_ts: datetime | None = None
    last_msg_ts: datetime | None = None
    first_token_ts: datetime | None = None
    last_token_ts: datetime | None = None
    quota_mentions = 0

    for message in messages:
        if not isinstance(message, dict):
            continue
        message_count += 1
        msg_type = message.get("type")
        ts = parse_iso(message.get("timestamp"))
        if ts is not None:
            if first_msg_ts is None or ts < first_msg_ts:
                first_msg_ts = ts
            if last_msg_ts is None or ts > last_msg_ts:
                last_msg_ts = ts

        text_chunks = _extract_text_fields(message.get("content"))
        text_chunks.extend(_extract_text_fields(message.get("displayContent")))
        content_blob = "\n".join(text_chunks).lower()
        if "quota" in content_blob or "/stats model" in content_blob:
            quota_mentions += 1

        if msg_type != "gemini":
            continue

        gemini_message_count += 1
        model = message.get("model")
        if isinstance(model, str) and model.strip():
            models[model] = models.get(model, 0) + 1

        usage = GeminiTokenUsage.from_mapping(message.get("tokens"))
        if usage.total_tokens <= 0:
            continue

        identity = _token_msg_identity(message)
        if identity in token_message_ids:
            continue
        token_message_ids.add(identity)
        tokens.add(usage)

        if ts is not None:
            if first_token_ts is None or ts < first_token_ts:
                first_token_ts = ts
            if last_token_ts is None or ts > last_token_ts:
                last_token_ts = ts

    return {
        "file": str(path),
        "session_id": session_id or path.stem,
        "kind": kind,
        "project_hash": project_hash,
        "start_time": start_time.isoformat() if start_time else None,
        "last_updated": last_updated.isoformat() if last_updated else None,
        "message_count": message_count,
        "gemini_message_count": gemini_message_count,
        "token_message_count": len(token_message_ids),
        "tokens": tokens.to_dict(),
        "models": models,
        "first_message_ts": first_msg_ts.isoformat() if first_msg_ts else None,
        "last_message_ts": last_msg_ts.isoformat() if last_msg_ts else None,
        "first_token_ts": first_token_ts.isoformat() if first_token_ts else None,
        "last_token_ts": last_token_ts.isoformat() if last_token_ts else None,
        "quota_mentions": quota_mentions,
    }


def scan_chat_file(path: Path) -> dict[str, Any]:
    if path.suffix == ".json":
        data = load_json(path)
        if isinstance(data, dict):
            return _parse_json_chat(path, data)
        raise ValueError(f"Unsupported JSON shape in {path}")
    if path.suffix == ".jsonl":
        return _parse_jsonl_chat(path)
    raise ValueError(f"Unsupported extension for chat file {path}")


def summarize_chats(gemini_home: Path, top_n: int) -> dict[str, Any]:
    files = iter_chat_files(gemini_home)
    parse_failures = 0
    reports: list[dict[str, Any]] = []
    agg_tokens = GeminiTokenUsage()
    models: dict[str, int] = {}
    sessions_seen: set[str] = set()
    total_messages = 0
    total_gemini_messages = 0
    total_token_messages = 0
    quota_mentions = 0
    date_start: datetime | None = None
    date_end: datetime | None = None
    token_start: datetime | None = None
    token_end: datetime | None = None
    session_start_min: datetime | None = None
    session_start_max: datetime | None = None

    for path in files:
        try:
            rep = scan_chat_file(path)
        except Exception:
            parse_failures += 1
            continue

        reports.append(rep)
        sessions_seen.add(str(rep["session_id"]))
        total_messages += int(rep["message_count"])
        total_gemini_messages += int(rep["gemini_message_count"])
        total_token_messages += int(rep["token_message_count"])
        quota_mentions += int(rep.get("quota_mentions") or 0)
        agg_tokens.add(GeminiTokenUsage.from_mapping(rep["tokens"]))

        for model, count in (rep.get("models") or {}).items():
            models[model] = models.get(model, 0) + int(count)

        fmsg = parse_iso(rep.get("first_message_ts"))
        lmsg = parse_iso(rep.get("last_message_ts"))
        ftok = parse_iso(rep.get("first_token_ts"))
        ltok = parse_iso(rep.get("last_token_ts"))
        sstart = parse_iso(rep.get("start_time"))

        if fmsg and (date_start is None or fmsg < date_start):
            date_start = fmsg
        if lmsg and (date_end is None or lmsg > date_end):
            date_end = lmsg
        if ftok and (token_start is None or ftok < token_start):
            token_start = ftok
        if ltok and (token_end is None or ltok > token_end):
            token_end = ltok
        if sstart and (session_start_min is None or sstart < session_start_min):
            session_start_min = sstart
        if sstart and (session_start_max is None or sstart > session_start_max):
            session_start_max = sstart

    top_sessions = sorted(reports, key=lambda r: int(r["tokens"]["total_tokens"]), reverse=True)

    return {
        "files_scanned": len(files),
        "files_failed": parse_failures,
        "session_count": len(sessions_seen),
        "message_count": total_messages,
        "gemini_message_count": total_gemini_messages,
        "token_message_count": total_token_messages,
        "quota_mentions_count": quota_mentions,
        "date_range_messages_start": date_start.isoformat() if date_start else None,
        "date_range_messages_end": date_end.isoformat() if date_end else None,
        "date_range_tokens_start": token_start.isoformat() if token_start else None,
        "date_range_tokens_end": token_end.isoformat() if token_end else None,
        "date_range_sessions_start": session_start_min.isoformat() if session_start_min else None,
        "date_range_sessions_end": session_start_max.isoformat() if session_start_max else None,
        "aggregate_tokens": agg_tokens.to_dict(),
        "models": dict(sorted(models.items(), key=lambda kv: kv[1], reverse=True)),
        "top_sessions_by_tokens": top_sessions[:top_n],
        "quota_structured_available": False,
        "quota_structured_note": (
            "No structured quota fields were found in local Gemini chat/session JSON files."
        ),
    }


def summarize_history(gemini_home: Path) -> dict[str, Any]:
    history_root = gemini_home / "history"
    if not history_root.exists():
        return {"path": str(history_root), "exists": False}

    files = [p for p in history_root.iterdir() if p.is_file()]
    entries = 0
    parse_failures = 0
    ts_min: datetime | None = None
    ts_max: datetime | None = None

    for path in files:
        obj = load_json(path)
        if not isinstance(obj, list):
            parse_failures += 1
            continue
        for item in obj:
            if not isinstance(item, dict):
                continue
            entries += 1
            ts = parse_iso(item.get("timestamp"))
            if ts and (ts_min is None or ts < ts_min):
                ts_min = ts
            if ts and (ts_max is None or ts > ts_max):
                ts_max = ts

    return {
        "path": str(history_root),
        "exists": True,
        "files_count": len(files),
        "entries_count": entries,
        "files_failed": parse_failures,
        "date_range_start": ts_min.isoformat() if ts_min else None,
        "date_range_end": ts_max.isoformat() if ts_max else None,
    }


def summarize_files(gemini_home: Path, top_n: int) -> dict[str, Any]:
    interesting = [
        gemini_home / "settings.json",
        gemini_home / "state.json",
        gemini_home / "projects.json",
        gemini_home / "oauth_creds.json",
        gemini_home / "google_accounts.json",
        gemini_home / "trustedFolders.json",
        gemini_home / "history",
        gemini_home / "tmp",
    ]
    inventory = [format_file_info(path) for path in interesting if path.is_file()]

    largest: list[dict[str, Any]] = []
    for path in gemini_home.rglob("*"):
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
    quota_used_percent = None
    context_used_percent = None

    footer_match = re.search(
        (
            r"quota\s+context[^\n]*\n[^\n]*?"
            r"([0-9]{1,3}(?:\.[0-9]+)?)%\s+used\s+([0-9]{1,3}(?:\.[0-9]+)?)%\s+used"
        ),
        clean_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if footer_match:
        quota_used_percent = float(footer_match.group(1))
        context_used_percent = float(footer_match.group(2))

    all_used = [float(x) for x in re.findall(r"([0-9]{1,3}(?:\.[0-9]+)?)%\s+used", clean_text)]
    if quota_used_percent is None and all_used:
        quota_used_percent = all_used[0]
        if len(all_used) > 1:
            context_used_percent = all_used[1]

    return {
        "quota_used_percent": quota_used_percent,
        "quota_remaining_percent": (
            max(0.0, 100.0 - quota_used_percent) if quota_used_percent is not None else None
        ),
        "context_used_percent": context_used_percent,
        "context_remaining_percent": (
            max(0.0, 100.0 - context_used_percent)
            if context_used_percent is not None
            else None
        ),
    }


def probe_live_quota(timeout_seconds: int, model: str = "gemini-2.5-flash") -> dict[str, Any]:
    """
    Always try to fetch live quota from Gemini CLI interactive footer and /stats command.
    """
    cmd = ["gemini", "--skip-trust", "-m", model]
    master_fd = None
    process = None
    raw_chunks: list[bytes] = []
    sent_stats = False
    sent_exit = False

    try:
        master_fd, slave_fd = pty.openpty()
        process = subprocess.Popen(
            cmd,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            close_fds=True,
        )
        os.close(slave_fd)

        start = time.monotonic()
        while (time.monotonic() - start) < timeout_seconds:
            if process.poll() is not None:
                break

            ready, _, _ = select.select([master_fd], [], [], 0.2)
            if ready:
                chunk = os.read(master_fd, 8192)
                if not chunk:
                    break
                raw_chunks.append(chunk)
                text = _strip_ansi(b"".join(raw_chunks).decode("utf-8", errors="replace"))

                if not sent_stats and (
                    "Type your message" in text
                    or "Ready (" in text
                    or "? for shortcuts" in text
                ):
                    os.write(master_fd, b"/stats model\n")
                    sent_stats = True

                if sent_stats and not sent_exit and (
                    "No API calls have been made in this session." in text
                    or "Model Usage Statistics" in text
                ):
                    os.write(master_fd, b"/exit\n")
                    sent_exit = True

            elapsed = time.monotonic() - start
            if not sent_stats and elapsed > min(4.0, timeout_seconds * 0.5):
                os.write(master_fd, b"/stats model\n")
                sent_stats = True
            if sent_stats and not sent_exit and elapsed > min(8.0, timeout_seconds * 0.8):
                os.write(master_fd, b"/exit\n")
                sent_exit = True

        if process.poll() is None:
            try:
                if master_fd is not None:
                    os.write(master_fd, b"/exit\n")
            except OSError:
                pass
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)

        output_text = _strip_ansi(b"".join(raw_chunks).decode("utf-8", errors="replace"))
        parsed = _extract_quota_from_interactive_output(output_text)
        return {
            "attempted": True,
            "method": "interactive-slash-stats-model",
            "model": model,
            "available": parsed["quota_used_percent"] is not None,
            "return_code": process.returncode if process else None,
            "sent_stats_command": sent_stats,
            "sent_exit_command": sent_exit,
            **parsed,
            "output_excerpt": output_text.strip()[:2000],
        }
    except FileNotFoundError:
        return {
            "attempted": True,
            "method": "interactive-slash-stats-model",
            "available": False,
            "error": "gemini command not found",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "attempted": True,
            "method": "interactive-slash-stats-model",
            "available": False,
            "error": str(exc),
        }
    finally:
        if master_fd is not None:
            try:
                os.close(master_fd)
            except OSError:
                pass


def build_report(
    gemini_home: Path,
    top_sessions: int,
    largest_files: int,
    quota_timeout: int,
) -> dict[str, Any]:
    report = {
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "gemini_home": str(gemini_home),
        "settings": summarize_settings(gemini_home),
        "projects": summarize_projects(gemini_home),
        "oauth": summarize_oauth(gemini_home),
        "accounts": summarize_accounts(gemini_home),
        "history": summarize_history(gemini_home),
        "chats": summarize_chats(gemini_home, top_n=top_sessions),
        "files": summarize_files(gemini_home, top_n=largest_files),
        "live_quota_probe": probe_live_quota(timeout_seconds=quota_timeout),
    }
    return report


def text_report(data: dict[str, Any], top_n: int) -> str:
    lines: list[str] = []
    lines.append("=== GEMINI LOCAL AUDIT ===")
    lines.append(f"Generated at: {data['generated_at']}")
    lines.append(f"Gemini home: {data['gemini_home']}")
    lines.append("")

    settings = data["settings"]
    lines.append("[Settings]")
    lines.append(f"- loaded: {settings.get('loaded')}")
    lines.append(f"- auth_selected_type: {settings.get('auth_selected_type')}")
    lines.append(f"- session_retention: {json.dumps(settings.get('session_retention'), ensure_ascii=False)}")
    lines.append(f"- ui_footer_items: {json.dumps(settings.get('ui_footer_items'), ensure_ascii=False)}")
    lines.append("")

    projects = data["projects"]
    lines.append("[Projects]")
    lines.append(f"- loaded: {projects.get('loaded')}")
    lines.append(f"- project_count: {fmt_int(projects.get('project_count'))}")
    lines.append("")

    oauth = data["oauth"]
    lines.append("[OAuth summary (sanitized)]")
    lines.append(f"- loaded: {oauth.get('loaded')}")
    lines.append(f"- token_type: {oauth.get('token_type')}")
    lines.append(f"- expiry_date_raw: {oauth.get('expiry_date_raw')}")
    lines.append(f"- id_token_exp: {oauth.get('id_token_exp')}")
    lines.append(
        f"- token_presence: {json.dumps(oauth.get('token_presence'), ensure_ascii=False)}"
    )
    lines.append(f"- scope_count: {fmt_int(oauth.get('scope_count'))}")
    lines.append("")

    accounts = data["accounts"]
    lines.append("[Google account summary]")
    lines.append(f"- loaded: {accounts.get('loaded')}")
    lines.append(f"- active_account_masked: {accounts.get('active_account_masked')}")
    lines.append(f"- old_accounts_count: {accounts.get('old_accounts_count')}")
    lines.append("")

    history = data["history"]
    lines.append("[History]")
    lines.append(f"- exists: {history.get('exists')}")
    if history.get("exists"):
        lines.append(f"- files_count: {fmt_int(history.get('files_count'))}")
        lines.append(f"- entries_count: {fmt_int(history.get('entries_count'))}")
        lines.append(f"- date_range: {history.get('date_range_start')} -> {history.get('date_range_end')}")
    lines.append("")

    chats = data["chats"]
    usage = GeminiTokenUsage.from_mapping(chats.get("aggregate_tokens"))
    lines.append("[Chat usage from ~/.gemini/tmp/**/chats]")
    lines.append(f"- files_scanned: {chats.get('files_scanned')} (failed: {chats.get('files_failed')})")
    lines.append(f"- session_count: {fmt_int(chats.get('session_count'))}")
    lines.append(f"- message_count: {fmt_int(chats.get('message_count'))}")
    lines.append(f"- gemini_message_count: {fmt_int(chats.get('gemini_message_count'))}")
    lines.append(f"- token_message_count: {fmt_int(chats.get('token_message_count'))}")
    lines.append(
        "- date_range_messages: "
        f"{chats.get('date_range_messages_start')} -> {chats.get('date_range_messages_end')}"
    )
    lines.append(
        "- date_range_tokens: "
        f"{chats.get('date_range_tokens_start')} -> {chats.get('date_range_tokens_end')}"
    )
    lines.append(
        "- date_range_sessions(startTime): "
        f"{chats.get('date_range_sessions_start')} -> {chats.get('date_range_sessions_end')}"
    )
    lines.append(
        "- aggregate_tokens: "
        f"input={fmt_int(usage.input_tokens)}, output={fmt_int(usage.output_tokens)}, "
        f"cached={fmt_int(usage.cached_tokens)}, thoughts={fmt_int(usage.thoughts_tokens)}, "
        f"tool={fmt_int(usage.tool_tokens)}, total={fmt_int(usage.total_tokens)}"
    )
    lines.append(f"- models: {json.dumps(chats.get('models'), ensure_ascii=False)}")
    lines.append(f"- quota_mentions_count: {fmt_int(chats.get('quota_mentions_count'))}")
    lines.append(f"- quota_structured_available: {chats.get('quota_structured_available')}")
    lines.append(f"- quota_note: {chats.get('quota_structured_note')}")
    lines.append("")

    lines.append(f"[Top {top_n} sessions by tokens]")
    for idx, session in enumerate(chats.get("top_sessions_by_tokens", []), start=1):
        tok = session.get("tokens") or {}
        lines.append(
            f"{idx}. session={session.get('session_id')} kind={session.get('kind')} "
            f"total={fmt_int(tok.get('total_tokens'))} input={fmt_int(tok.get('input_tokens'))} "
            f"output={fmt_int(tok.get('output_tokens'))} cached={fmt_int(tok.get('cached_tokens'))}"
        )
        lines.append(f"   file={session.get('file')}")

    live_probe = data.get("live_quota_probe")
    if isinstance(live_probe, dict):
        lines.append("")
        lines.append("[Live quota]")
        lines.append(f"- attempted: {live_probe.get('attempted')}")
        lines.append(f"- method: {live_probe.get('method')}")
        lines.append(f"- available: {live_probe.get('available')}")
        if live_probe.get("error") is not None:
            lines.append(f"- error: {live_probe.get('error')}")
        lines.append(f"- return_code: {live_probe.get('return_code')}")
        lines.append(
            f"- quota_used_percent: {live_probe.get('quota_used_percent')} "
            f"(remaining={live_probe.get('quota_remaining_percent')})"
        )
        lines.append(
            f"- context_used_percent: {live_probe.get('context_used_percent')} "
            f"(remaining={live_probe.get('context_remaining_percent')})"
        )

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Audit local Gemini CLI data from ~/.gemini "
            "(session tokens, date ranges, local files, and live quota probing)."
        )
    )
    parser.add_argument(
        "--gemini-home",
        type=Path,
        default=Path.home() / ".gemini",
        help="Path to Gemini home directory (default: ~/.gemini)",
    )
    parser.add_argument(
        "--top-sessions",
        type=int,
        default=15,
        help="Number of top sessions by tokens to include (default: 15)",
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
        help="Timeout in seconds for live interactive quota probe (default: 20)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    gemini_home = args.gemini_home.expanduser().resolve()
    if not gemini_home.exists():
        print(f"Error: {gemini_home} does not exist.")
        return 2

    report = build_report(
        gemini_home=gemini_home,
        top_sessions=max(1, args.top_sessions),
        largest_files=max(1, args.largest_files),
        quota_timeout=max(5, args.quota_timeout),
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
