"""Structured logging helpers with secret-safe payloads."""

import json
import logging
import time

_SECRET_KEYS = {"authorization", "token", "cookie", "refresh_token", "bearer"}


def _sanitize(data: dict[str, object]) -> dict[str, object]:
    """Redact likely secret-bearing keys from a log payload."""

    sanitized: dict[str, object] = {}
    for key, value in data.items():
        if any(secret_key in key.lower() for secret_key in _SECRET_KEYS):
            sanitized[key] = "[REDACTED]"
        else:
            sanitized[key] = value
    return sanitized


def configure_logging(level: str = "INFO") -> None:
    """Configure the root logger."""

    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO), format="%(message)s")


def log_operation(
    logger: logging.Logger,
    provider_id: str,
    operation: str,
    outcome: str,
    started_at: float,
    error_summary: str | None = None,
    extra: dict[str, object] | None = None,
) -> None:
    """Emit a structured operation log line."""

    payload: dict[str, object] = {
        "provider_id": provider_id,
        "operation": operation,
        "outcome": outcome,
        "elapsed_ms": int((time.time() - started_at) * 1000),
        "error_summary": error_summary,
    }
    if extra:
        payload.update(_sanitize(extra))
    logger.info(json.dumps(payload, ensure_ascii=True))
