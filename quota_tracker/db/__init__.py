"""Database layer: schema, records, and CRUD helpers."""

from quota_tracker.db.queries import (
    get_provider_row,
    insert_quota,
    insert_token_usage,
    list_provider_health,
    list_provider_rows,
    update_provider_row,
    upsert_session,
)
from quota_tracker.db.records import QuotaRecord, SessionRecord, TokenUsageRecord
from quota_tracker.db.schema import (
    PROVIDERS,
    apply_migrations,
    connect_db,
    deterministic_session_id,
    ensure_provider,
    run_maintenance,
    utc_now_iso,
    validate_json_text,
    write_transaction,
)

__all__ = [
    "PROVIDERS",
    "QuotaRecord",
    "SessionRecord",
    "TokenUsageRecord",
    "apply_migrations",
    "connect_db",
    "deterministic_session_id",
    "ensure_provider",
    "get_provider_row",
    "insert_quota",
    "insert_token_usage",
    "list_provider_health",
    "list_provider_rows",
    "run_maintenance",
    "update_provider_row",
    "upsert_session",
    "utc_now_iso",
    "validate_json_text",
    "write_transaction",
]
