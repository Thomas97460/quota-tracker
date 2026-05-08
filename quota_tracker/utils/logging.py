"""Structured logging for quota_tracker."""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any


class StructuredFormatter(logging.Formatter):
    """Formatter that outputs JSON for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record as a JSON string."""
        # Use UTC timestamp
        timestamp = datetime.fromtimestamp(record.created, tz=UTC).isoformat()

        log_data: dict[str, Any] = {
            "timestamp": timestamp,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add structured data if present
        if hasattr(record, "structured_data"):
            structured_data = record.structured_data
            if isinstance(structured_data, dict):
                # Security: Strictly ensure no sensitive keys are logged
                # We only allow a predefined set of fields for operation logging
                # and sanitize any other fields if they were to be added.
                safe_data = {}
                allowed_fields = {
                    "provider_id",
                    "operation_name",
                    "outcome",
                    "elapsed_time",
                    "error_summary",
                }

                for key, value in structured_data.items():
                    if key in allowed_fields:
                        safe_data[key] = value
                    else:
                        # For any extra fields, we apply a strict filter
                        key_lower = key.lower()
                        if any(
                            s in key_lower
                            for s in [
                                "secret",
                                "cookie",
                                "token",
                                "key",
                                "password",
                                "auth",
                                "content",
                                "body",
                            ]
                        ):
                            safe_data[key] = "[REDACTED]"
                        else:
                            safe_data[key] = value
                log_data.update(safe_data)

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)


def setup_logging(level: int | str = logging.INFO) -> None:
    """Set up the root logger for quota_tracker."""
    root_logger = logging.getLogger("quota_tracker")
    root_logger.setLevel(level)

    # Prevent duplicate handlers if setup is called multiple times
    if not root_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(StructuredFormatter())
        root_logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Get a named logger under the quota_tracker namespace."""
    return logging.getLogger(f"quota_tracker.{name}")


def log_operation(
    logger: logging.Logger,
    provider_id: str,
    operation_name: str,
    outcome: str,
    elapsed_time: float,
    error_summary: str | None = None,
) -> None:
    """
    Log a provider operation with structured data.

    Args:
        logger: The logger to use.
        provider_id: The ID of the provider (e.g., 'gemini', 'copilot').
        operation_name: The name of the operation (e.g., 'scan', 'probe').
        outcome: The result of the operation (e.g., 'success', 'failure').
        elapsed_time: Time taken in seconds.
        error_summary: A brief summary of the error, if any.
    """
    structured_data = {
        "provider_id": provider_id,
        "operation_name": operation_name,
        "outcome": outcome,
        "elapsed_time": elapsed_time,
        "error_summary": error_summary,
    }

    logger.info(
        f"Operation {operation_name} for {provider_id}: {outcome}",
        extra={"structured_data": structured_data},
    )
