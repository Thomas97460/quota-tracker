"""Integration test for Codex provider snapshots."""

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from quota_tracker.providers.codex import CodexProvider


def json_serial(obj: Any) -> str:
    """JSON serializer for objects not serializable by default json code"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


def test_codex_snapshots() -> None:
    snapshot_root = Path("tests/snapshots/codex")
    if not snapshot_root.exists():
        pytest.skip("No codex snapshots found")

    for snapshot_dir in snapshot_root.iterdir():
        if not snapshot_dir.is_dir():
            continue

        input_dir = snapshot_dir / "input"
        expected_file = snapshot_dir / "expected.json"

        provider = CodexProvider()
        records = list(provider.scan_passive(str(input_dir)))

        # Sort records to be deterministic for comparison
        sessions = sorted(
            [asdict(r) for r in records if r.__class__.__name__ == "SessionRecord"],
            key=lambda x: x["external_session_id"],
        )
        tokens = sorted(
            [asdict(r) for r in records if r.__class__.__name__ == "TokenUsageRecord"],
            key=lambda x: (x["external_session_id"], x["external_event_id"]),
        )
        quotas = sorted(
            [asdict(r) for r in records if r.__class__.__name__ == "QuotaRecord"],
            key=lambda x: (x["quota_name"], x["timestamp"]),
        )

        actual_data = {
            "sessions": sessions,
            "token_usage": tokens,
            "quotas": quotas,
        }

        # If expected file doesn't exist, we can use this to generate it
        if not expected_file.exists():
            expected_file.write_text(
                json.dumps(actual_data, indent=2, default=json_serial)
            )
            continue

        expected_data = json.loads(expected_file.read_text())
        actual_data_json = json.loads(json.dumps(actual_data, default=json_serial))

        assert actual_data_json == expected_data, (
            f"Snapshot mismatch for {snapshot_dir}"
        )


def test_codex_incremental() -> None:
    snapshot_dir = Path("tests/snapshots/codex/0.1.0")
    if not snapshot_dir.exists():
        pytest.skip("Base snapshot for incremental test not found")

    input_dir = snapshot_dir / "input"

    provider = CodexProvider()
    sync_state: dict[str, Any] = {}

    # First pass
    records1 = list(provider.scan_incremental(str(input_dir), sync_state))
    # 1 session from JSONL + 1 session from state_db = 2 sessions
    # 1 token from JSONL + 1 token from state_db + 1 token from logs_db = 3 tokens
    # 1 quota from JSONL = 1 quota
    # Total = 6 records
    assert len(records1) == 6
    
    # Check sync state keys
    assert str(input_dir / "sessions/session-1.jsonl") in sync_state
    assert f"{input_dir / 'state_5.sqlite'}:last_updated" in sync_state
    assert f"{input_dir / 'logs_2.sqlite'}:last_ts" in sync_state

    # Second pass - no changes
    records2 = list(provider.scan_incremental(str(input_dir), sync_state))
    assert len(records2) == 0

    # Modify JSONL file
    path = input_dir / "sessions/session-1.jsonl"
    path.touch()

    # Third pass - should re-read modified file
    records3 = list(provider.scan_incremental(str(input_dir), sync_state))
    # It will yield 1 SessionRecord, 1 TokenUsageRecord,
    # and 1 QuotaRecord from session-1.jsonl
    assert len(records3) == 3
