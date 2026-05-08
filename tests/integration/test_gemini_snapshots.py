"""Integration test for Gemini provider snapshots."""

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from quota_tracker.providers.gemini import GeminiProvider


def json_serial(obj: Any) -> str:
    """JSON serializer for objects not serializable by default json code"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


def test_gemini_snapshots() -> None:
    snapshot_root = Path("tests/snapshots/gemini")
    if not snapshot_root.exists():
        pytest.skip("No gemini snapshots found")

    for snapshot_dir in snapshot_root.iterdir():
        if not snapshot_dir.is_dir():
            continue

        input_dir = snapshot_dir / "input"
        expected_file = snapshot_dir / "expected.json"

        provider = GeminiProvider()
        records = list(provider.scan_passive(str(input_dir)))

        # Sort records to be deterministic for comparison
        # Sessions first, then TokenUsageRecords sorted by session_id and event_id
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


def test_gemini_incremental() -> None:
    snapshot_dir = Path("tests/snapshots/gemini/0.1.0")
    if not snapshot_dir.exists():
        pytest.skip("Base snapshot for incremental test not found")

    input_dir = snapshot_dir / "input"

    provider = GeminiProvider()
    sync_state: dict[str, Any] = {}

    # First pass
    records1 = list(provider.scan_incremental(str(input_dir), sync_state))
    assert len(records1) == 4
    assert len(sync_state) == 2  # session-1.json and session-2.jsonl

    # Second pass - no changes
    records2 = list(provider.scan_incremental(str(input_dir), sync_state))
    assert len(records2) == 0

    # Modify a file (change mtime)
    path = input_dir / "tmp/chats/session-1.json"
    path.touch()

    # Third pass - should re-read modified file
    records3 = list(provider.scan_incremental(str(input_dir), sync_state))
    # It will yield 1 SessionRecord and 1 TokenUsageRecord for session-1
    assert len(records3) == 2

    from quota_tracker.core.models import SessionRecord

    assert isinstance(records3[0], SessionRecord)
    assert records3[0].external_session_id == "session-1"
