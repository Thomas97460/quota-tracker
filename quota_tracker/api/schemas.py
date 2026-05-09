"""Pydantic request payloads exposed by the HTTP API."""

from __future__ import annotations

from pydantic import BaseModel


class ProviderActionRequest(BaseModel):
    """Manual provider action payload."""

    full_rescan: bool = False


class ProviderPatchRequest(BaseModel):
    """Provider configuration patch payload."""

    enabled: bool | None = None
    home_path: str | None = None
    active_probe_enabled: bool | None = None
    passive_sync_enabled: bool | None = None


class ConfigPatchRequest(BaseModel):
    """Global config patch payload."""

    sync_interval_minutes: int | None = None
    active_probe_interval_minutes: int | None = None
    passive_sync_interval_minutes: int | None = None
    web_host: str | None = None
    web_port: int | None = None
    database_path: str | None = None
    log_level: str | None = None
