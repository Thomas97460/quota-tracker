# Plan: Quota Tracker Daemon

## Overview
A lightweight Linux daemon to track AI provider quotas and session history (Gemini, Codex, Copilot). Data is stored in a structured, normalized SQLite database for local auditing and visualization via a React dashboard.

## Tech Stack
- **Daemon**: Python 3.11+
- **Database**: SQLite (Common schema for all providers)
- **Web Server**: Lightweight Python server (e.g., FastAPI/Starlette) to serve the API and React build.
- **Frontend**: React (TypeScript) + ECharts
- **Quality**:
  - `ruff` (format & check)
  - `mypy` (strict typing)
  - `interrogate` (100% docstring coverage)
  - `pytest` (100% code coverage)

## Installation & Setup
- **One-liner**: Installable via `curl -sSL ... | sh`.
- **Idempotency**: Multiple runs of the script yield the same consistent state. Existing configurations are updated, not duplicated.
- **Interactive Configuration**:
  - **Provider Selection**: Auto-detects available providers and asks to enable all or select a specific subset.
  - **Re-configuration**: Re-running the script allows adding/removing providers; the daemon and database adapt transparently.
  - **Service**: Automatically configures/updates a `systemd` unit.

## Functional Requirements
- **Data Collection**:
  - **Quotas**: Poll every $Y$ seconds (live status).
  - **History**: Poll every $X$ minutes (extract token usage).
- **Sync Strategy**:
  - **Initial Scan**: On first run or when a new provider is added, perform a full historical scan of logs and databases.
  - **Incremental Updates**: Use "high-water marks" (tracking the last processed timestamp, row ID, or file offset) to only process new data in subsequent scans.
  - **Resilience**: Ensure data integrity if the daemon is restarted or if providers are toggled.
- **Normalized Data**: Providers (Gemini, Codex, Copilot) must normalize their data into a common format before storage. No provider-specific tables.
- **Frontend Views**: 
  - Global overview (all providers combined).
  - Individual provider drill-down.
- **Performance**: Minimal RAM/CPU footprint; lean storage (no session content).

## Database Storage (Schema)
The database uses a normalized structure with `JSON` blobs for extensibility without schema migrations.

### 1. `providers`
Basic configuration for each AI provider.
- `id`: (PK) string (e.g., "gemini", "codex").
- `enabled`: boolean.
- `config`: JSON (polling intervals, paths, etc.).

### 2. `quota_history`
Periodic snapshots of provider limits.
- `provider_id`: (FK)
- `timestamp`: UTC DateTime.
- `used_percent`: float.
- `remaining_percent`: float.
- `window_minutes`: integer.
- `resets_at`: UTC DateTime.
- `raw_data`: JSON (original provider response for future metrics).

### 3. `sessions`
Registry of unique AI sessions.
- `id`: (PK) Internal unique ID.
- `provider_id`: (FK).
- `external_session_id`: string (original ID from provider).
- `model_name`: string.
- `project_path`: string (Absolute path to the project/directory).
- `project_name`: string (Folder name or provider-specific project ID).
- `created_at`: UTC DateTime.
- `last_seen_at`: UTC DateTime.
- `metadata`: JSON (CLI version, project hash, etc.).

### 4. `token_usage_history`
Granular token consumption records.
- `session_id`: (FK).
- `timestamp`: UTC DateTime.
- `input_tokens`: integer.
- `output_tokens`: integer.
- `cached_tokens`: integer.
- `reasoning_tokens`: integer.
- `thoughts_tokens`: integer.
- `tool_tokens`: integer.
- `total_tokens`: integer.
- `raw_data`: JSON (original usage breakdown).
