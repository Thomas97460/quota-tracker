"""Provider package: contract, normalization, and concrete implementations."""

from quota_tracker.providers.base import (
    PassiveSyncResult,
    Provider,
    ProviderMetadata,
    normalize_quota,
    normalize_session,
    normalize_token_usage,
)
from quota_tracker.providers.codex import CodexProvider
from quota_tracker.providers.copilot import CopilotProvider
from quota_tracker.providers.gemini import GeminiProvider

__all__ = [
    "CodexProvider",
    "CopilotProvider",
    "GeminiProvider",
    "PassiveSyncResult",
    "Provider",
    "ProviderMetadata",
    "normalize_quota",
    "normalize_session",
    "normalize_token_usage",
]
