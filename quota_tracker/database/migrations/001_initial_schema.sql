-- Initial schema for quota-tracker

-- Internal table for tracking migrations
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Providers table
CREATE TABLE IF NOT EXISTS providers (
    id TEXT PRIMARY KEY CHECK (id IN ('gemini', 'codex', 'copilot')),
    enabled BOOLEAN NOT NULL DEFAULT 1,
    config TEXT NOT NULL, -- JSON
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Quota history table
CREATE TABLE IF NOT EXISTS quota_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_id TEXT NOT NULL,
    quota_name TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    used_percent REAL,
    remaining_percent REAL,
    window_minutes INTEGER,
    resets_at TEXT,
    source TEXT NOT NULL,
    raw_data TEXT, -- JSON
    created_at TEXT NOT NULL,
    FOREIGN KEY (provider_id) REFERENCES providers(id)
);

CREATE INDEX idx_quota_history_provider_ts ON quota_history(provider_id, timestamp);
CREATE INDEX idx_quota_history_quota_name ON quota_history(quota_name);
CREATE INDEX idx_quota_history_resets_at ON quota_history(resets_at);

-- Sessions table
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY, -- Deterministic: provider_id:external_session_id
    provider_id TEXT NOT NULL,
    external_session_id TEXT NOT NULL,
    model_name TEXT NOT NULL DEFAULT 'unknown',
    project_path TEXT,
    project_name TEXT,
    created_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    metadata TEXT, -- JSON
    FOREIGN KEY (provider_id) REFERENCES providers(id)
);

CREATE INDEX idx_sessions_provider ON sessions(provider_id);
CREATE INDEX idx_sessions_project ON sessions(project_name);
CREATE INDEX idx_sessions_model ON sessions(model_name);

-- Token usage history table
CREATE TABLE IF NOT EXISTS token_usage_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    provider_id TEXT NOT NULL,
    external_event_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    model_name TEXT NOT NULL DEFAULT 'unknown',
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cached_tokens INTEGER NOT NULL DEFAULT 0,
    reasoning_tokens INTEGER NOT NULL DEFAULT 0,
    thoughts_tokens INTEGER NOT NULL DEFAULT 0,
    tool_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL,
    raw_data TEXT, -- JSON
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id),
    FOREIGN KEY (provider_id) REFERENCES providers(id),
    UNIQUE(provider_id, session_id, external_event_id)
);

CREATE INDEX idx_token_usage_session ON token_usage_history(session_id);
CREATE INDEX idx_token_usage_provider_ts ON token_usage_history(provider_id, timestamp);
