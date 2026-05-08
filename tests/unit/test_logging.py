"""Tests for structured logging."""

import json
import logging
from io import StringIO

from quota_tracker.utils.logging import (
    StructuredFormatter,
    log_operation,
)


def test_structured_formatter_basic() -> None:
    """Test that StructuredFormatter outputs JSON with basic fields."""
    formatter = StructuredFormatter()
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Test message",
        args=(),
        exc_info=None,
    )

    output = formatter.format(record)
    data = json.loads(output)

    assert data["level"] == "INFO"
    assert data["logger"] == "test_logger"
    assert data["message"] == "Test message"
    assert "timestamp" in data


def test_structured_formatter_with_data() -> None:
    """Test that StructuredFormatter includes structured data."""
    formatter = StructuredFormatter()
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Operation message",
        args=(),
        exc_info=None,
    )
    record.structured_data = {
        "provider_id": "gemini",
        "operation_name": "probe",
        "outcome": "success",
        "elapsed_time": 1.23,
    }

    output = formatter.format(record)
    data = json.loads(output)

    assert data["provider_id"] == "gemini"
    assert data["operation_name"] == "probe"
    assert data["outcome"] == "success"
    assert data["elapsed_time"] == 1.23


def test_structured_formatter_redaction() -> None:
    """Test that StructuredFormatter redacts sensitive information."""
    formatter = StructuredFormatter()
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Sensitive message",
        args=(),
        exc_info=None,
    )
    record.structured_data = {
        "my_secret": "password123",
        "cookie_value": "session=abc",
        "auth_token": "token-xyz",
        "safe_field": "safe",
    }

    output = formatter.format(record)
    data = json.loads(output)

    assert data["my_secret"] == "[REDACTED]"
    assert data["cookie_value"] == "[REDACTED]"
    assert data["auth_token"] == "[REDACTED]"
    assert data["safe_field"] == "safe"


def test_log_operation() -> None:
    """Test the log_operation helper."""
    # Setup a logger with our formatter
    logger = logging.getLogger("test_op_logger")
    logger.setLevel(logging.INFO)

    buffer = StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setFormatter(StructuredFormatter())
    logger.addHandler(handler)

    log_operation(
        logger,
        provider_id="copilot",
        operation_name="scan",
        outcome="failure",
        elapsed_time=0.5,
        error_summary="Timeout",
    )

    output = buffer.getvalue()
    data = json.loads(output)

    assert data["provider_id"] == "copilot"
    assert data["operation_name"] == "scan"
    assert data["outcome"] == "failure"
    assert data["elapsed_time"] == 0.5
    assert data["error_summary"] == "Timeout"
