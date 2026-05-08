"""Structured logging for quota-tracker."""

import logging
import sys
from typing import Any

from quota_tracker.core.config import AppConfig


def setup_logging(config: AppConfig) -> None:
    """
    Setup structured logging for the application.

    Args:
        config: Application configuration containing log level.
    """
    log_level = getattr(logging, config.global_settings.log_level.upper(), logging.INFO)
    
    # Configure logging to stdout for daemon/CLI usage
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        stream=sys.stdout
    )


def log_operation(
    provider_id: str,
    operation: str,
    outcome: str,
    elapsed_time: float,
    error_summary: str | None = None,
    **kwargs: Any
) -> None:
    """
    Log a structured operation event.

    Args:
        provider_id: The provider ID.
        operation: The operation name.
        outcome: The outcome (e.g., 'success', 'failure').
        elapsed_time: Elapsed time in seconds.
        error_summary: Optional error summary.
        **kwargs: Additional metadata to log.
    """
    logger = logging.getLogger("quota_tracker")
    
    log_data = {
        "provider_id": provider_id,
        "operation": operation,
        "outcome": outcome,
        "elapsed_time": round(elapsed_time, 4),
        "error_summary": error_summary,
        **kwargs
    }
    
    # Filter out any keys that might contain secrets if passed by mistake
    # Currently, we just log the dictionary representation
    logger.info(f"Operation event: {log_data}")
