"""Tests for structured logging helpers."""

from __future__ import annotations

import json
import logging

import pytest

from quota_tracker.logging import configure_logging, log_operation


def test_configure_logging_and_log_operation(caplog: pytest.LogCaptureFixture) -> None:
    configure_logging("INFO")
    logger = logging.getLogger("quota-tracker-test")
    with caplog.at_level(logging.INFO):
        log_operation(
            logger=logger,
            provider_id="codex",
            operation="scan",
            outcome="ok",
            started_at=0.0,
            error_summary=None,
            extra={"authorization": "secret", "count": 1},
        )
    payload = json.loads(caplog.records[-1].message)
    assert payload["provider_id"] == "codex"
    assert payload["operation"] == "scan"
    assert payload["outcome"] == "ok"
    assert payload["authorization"] == "[REDACTED]"
    assert payload["count"] == 1
    assert "elapsed_ms" in payload
