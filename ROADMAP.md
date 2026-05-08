# ROADMAP - Quota Tracker Daemon

This roadmap is written for coding agents that should implement, not redesign. Do not make architectural choices while coding. If a task below is ambiguous, stop and record the blocker instead of inventing a different architecture.

The existing scripts are R&D references only:

- `gemini_local_audit.py`
- `codex_local_audit.py`
- `copilot_local_audit.py`
- `get_weekly_quota.py`
- `copilot_report.md`
- files under `analysis/`

They prove where the data lives and how live quota probes work. The production implementation must rewrite and integrate the behavior into a clean application structure.

## Non-Negotiable Implementation Decisions

- [ ] Build a complete application, not a larger pile of audit scripts.
- [ ] Use Python 3.12+ for the daemon, API, CLI, migrations, provider parsing, and quota probes.
- [ ] Use FastAPI as the only HTTP framework.
- [ ] Use SQLite as the only persistent database.
- [ ] Use the Python standard `sqlite3` module and explicit SQL migrations for V1. Do not introduce an ORM.
- [ ] Use React, TypeScript, Vite, and ECharts for the frontend.
- [ ] Expose exactly one user-facing HTTP port in runtime mode.
- [ ] Serve both `/api/...` JSON endpoints and the built React app from the same FastAPI process.
- [ ] Do not run a separate frontend server in production.
- [ ] The frontend must never read SQLite directly. It must call relative `/api/...` endpoints.
- [ ] Store provider data in normalized common tables only. Do not create Gemini, Codex, or Copilot specific tables.
- [ ] Do not store prompt text, assistant text, command text, or full conversation content in the database.
- [ ] Store raw provider payloads only when they are quota/usage metadata and do not contain conversation content or secrets.
- [ ] Never log, persist, or return OAuth tokens, GitHub tokens, cookies, bearer tokens, refresh tokens, or raw authorization headers.
- [ ] Treat active quota probes as potentially billable or quota-consuming calls. They must be configurable and test-mocked by default.
- [ ] All timestamps stored in SQLite must be UTC ISO 8601 strings.
- [ ] All provider output must be normalized before storage.

## Technical References From Existing Scripts

### Gemini

- [ ] Use `gemini_local_audit.py` as the reference for local file discovery and quota probing.
- [ ] Default home path: `~/.gemini`.
- [ ] Local history paths to support:
  - `~/.gemini/tmp/**/chats/session-*.json`
  - `~/.gemini/tmp/**/chats/session-*.jsonl`
  - `~/.gemini/tmp/**/chats/*/*.json`
  - `~/.gemini/tmp/**/chats/*/*.jsonl`
- [ ] Local config/auth files to inspect without leaking secrets:
  - `~/.gemini/settings.json`
  - `~/.gemini/oauth_creds.json`
  - `~/.gemini/accounts.json`
  - `~/.gemini/projects.json`
- [ ] Token fields to normalize:
  - `input_tokens`
  - `output_tokens`
  - `cached_tokens`
  - `thoughts_tokens`
  - `tool_tokens`
  - `total_tokens`
- [ ] Active quota probe:
  - Use OAuth credentials from `oauth_creds.json`.
  - Refresh the access token when expired.
  - Call Code Assist `loadCodeAssist`.
  - Call Code Assist `retrieveUserQuota`.
  - Convert each returned bucket into a normalized quota snapshot with used percent, remaining percent, reset time, model id, token type, and raw metadata.
- [ ] The Gemini fallback through interactive `/stats model` is allowed only as a secondary fallback when Code Assist quota probing fails and must be disabled in automated tests.

### Codex

- [ ] Use `codex_local_audit.py` as the reference for local file discovery, token parsing, SQLite inspection, and WHAM usage probing.
- [ ] Default home path: `~/.codex`.
- [ ] Local files and databases to support:
  - `~/.codex/auth.json`
  - `~/.codex/config.toml`
  - `~/.codex/version.json`
  - `~/.codex/sessions/**/*.jsonl`
  - `~/.codex/archived_sessions/*.jsonl`
  - `~/.codex/state_5.sqlite`
  - `~/.codex/logs_2.sqlite`
- [ ] Token fields to normalize:
  - `input_tokens`
  - `cached_input_tokens` mapped to `cached_tokens`
  - `output_tokens`
  - `reasoning_output_tokens` mapped to `reasoning_tokens`
  - `total_tokens`
- [ ] Rate limit fields to normalize when present in session files:
  - primary window used percent
  - primary remaining percent
  - primary window minutes
  - primary reset timestamp
  - secondary window used percent
  - secondary remaining percent
  - secondary window minutes
  - secondary reset timestamp
- [ ] WHAM usage probing:
  - Use the local access token only in memory.
  - Call `https://chatgpt.com/backend-api/wham/usage`.
  - Store only quota/usage metadata, never tokens.
  - Mock this probe in tests.

### Copilot

- [ ] Use `copilot_local_audit.py`, `get_weekly_quota.py`, `copilot_report.md`, and `analysis/` as references for local parsing and precise weekly quota probing.
- [ ] Default home path: `~/.copilot`.
- [ ] Local files to support:
  - `~/.copilot/config.json`
  - `~/.copilot/command-history-state.json`
  - `~/.copilot/session-state/**/events.jsonl`
- [ ] Token fields to normalize:
  - `inputTokens` or `input_tokens`
  - `outputTokens` or `output_tokens`
  - `cacheReadTokens` or `cache_read_tokens` mapped to `cached_tokens`
  - `cacheWriteTokens` or `cache_write_tokens` stored inside raw metadata
  - `reasoningTokens` or `reasoning_tokens`
  - `totalTokens` or `total_tokens`
- [ ] Precise weekly quota probe:
  - Read the local Copilot token from `~/.copilot/config.json` in memory only.
  - Resolve the model API endpoint through `https://api.github.com/copilot_internal/user`.
  - Send a minimal Copilot chat completion request using a known supported low-cost model.
  - Parse `x-usage-ratelimit-weekly`.
  - Compute `used_percent = 100 - rem`.
  - Store `remaining_percent = rem`.
  - Store `resets_at = rst`.
  - Store the parsed header metadata in `raw_data`.
- [ ] Copilot quota headers to parse:
  - `x-usage-ratelimit-weekly`
  - `x-usage-ratelimit-session`
  - `x-quota-snapshot-chat`
  - `x-quota-snapshot-completions`
  - `x-quota-snapshot-premium_interactions`
- [ ] Copilot entitlement probe:
  - Keep it separate from the weekly probe.
  - Use it only for monthly/premium request quota metadata.
  - Do not treat entitlement data as the weekly quota source.
- [ ] Copilot command history must be sanitized before any display or persistence. Persist no raw cookie-bearing command.

## Implementation Roadmap

### 1. Repository And Application Foundation

- [x] Create a Python package named `quota_tracker`.
  - [x] Move production logic into the package instead of extending the existing audit scripts.
  - [x] Keep the existing scripts available as references until equivalent production behavior is implemented and tested.
  - [x] Add a single installed CLI command named `quota-tracker`.
- [x] Add project packaging and tool configuration.
  - [x] Define Python dependencies for FastAPI, Uvicorn, Pydantic, pytest, ruff, mypy, and interrogate.
  - [x] Define frontend tooling for Vite, React, TypeScript, and ECharts.
  - [x] Configure `ruff`, `mypy`, `pytest`, and `interrogate` in the project configuration.
- [x] Add a root `Taskfile.yml` as the canonical command registry.
  - [x] Every documented development, validation, build, test, install, run, and cleanup command must be available as a `task` target.
  - [x] The README and developer docs must reference `task` targets instead of duplicating raw shell command sequences.
  - [x] Each task must be deterministic from the repository root and must avoid depending on the caller's current subdirectory.
  - [x] Task names must be stable and descriptive: `setup`, `format`, `lint`, `typecheck`, `docstrings`, `test`, `test-unit`, `test-integration`, `test-snapshots`, `test-frontend`, `build-frontend`, `nix-check`, `validate`, `validate:quiet`, `run-api`, `run-daemon`, `scan`, `probe`, `migrate`, `install-user-service`, and `clean`.
  - [x] `task validate` must run all required local validation gates in a normal developer-readable mode.
  - [x] `task validate:quiet` must run the same validation gates as `task validate` with silent success output.
  - [x] `task validate:quiet` must print nothing when every validation gate succeeds except an optional final one-line success summary.
  - [x] On failure, `task validate:quiet` must stop at the first failing gate and print only the failing task name, exit code, raw command, and the first 120 lines of captured output.
  - [x] On failure, `task validate:quiet` must also print the path to a full temporary log file for the failing command.
  - [x] `task validate:quiet` must prefer non-verbose command modes when available, for example quiet pytest output or non-verbose frontend build output.
  - [x] `task validate:quiet` must not hide the failure reason completely; the first 120 lines must be enough to identify the failing subsystem.
- [x] Define application directories.
  - [x] Default config directory: `~/.config/quota-tracker`.
  - [x] Default database path: `~/.local/share/quota-tracker/quota-tracker.sqlite3`.
  - [x] Default log directory: `~/.local/state/quota-tracker/logs`.
  - [x] Default web host: `127.0.0.1`.
  - [x] Default web port: `8787`.
- [ ] Define the config file format.
  - [ ] Store config as JSON at `~/.config/quota-tracker/config.json`.
  - [ ] Include global daemon settings: active probe interval minutes, passive sync interval minutes, web host, web port, database path, log level.
  - [ ] Include provider settings for `gemini`, `codex`, and `copilot`: enabled flag, home path, active probe enabled flag, passive sync enabled flag, provider-specific safe options.
  - [ ] Include no secrets in config.
- [ ] Implement structured logging.
  - [ ] Log provider id, operation name, outcome, elapsed time, and error summary.
  - [ ] Do not log secret values, raw cookies, raw tokens, or conversation content.
  - [ ] Make logs useful for daemon troubleshooting without requiring debug secrets.

### 2. SQLite Schema And Migrations

- [ ] Implement idempotent SQLite migrations.
  - [ ] Store migration state in a generic internal table named `schema_migrations`.
  - [ ] Running migrations twice must not change existing data.
  - [ ] Opening the application must apply pending migrations before any scan or API read.
- [ ] Implement the `providers` table.
  - [ ] Columns: `id`, `enabled`, `config`, `created_at`, `updated_at`.
  - [ ] `id` values must be exactly `gemini`, `codex`, and `copilot`.
  - [ ] `config` must be JSON text containing provider paths, intervals, high-water marks, and safe provider options.
- [ ] Implement the `quota_history` table.
  - [ ] Required PLAN fields: `provider_id`, `timestamp`, `used_percent`, `remaining_percent`, `window_minutes`, `resets_at`, `raw_data`.
  - [ ] Add generic V1 fields: `id`, `quota_name`, `source`, `created_at`.
  - [ ] `quota_name` examples: `default`, `primary`, `secondary`, `weekly`, `session`, `monthly`, `premium_interactions`, `chat`, `completions`.
  - [ ] `source` examples: `active_probe`, `local_log`, `provider_db`.
  - [ ] Add indexes on provider id, timestamp, quota name, and reset time.
- [ ] Implement the `sessions` table.
  - [ ] Required PLAN fields: `id`, `provider_id`, `external_session_id`, `model_name`, `project_path`, `project_name`, `created_at`, `last_seen_at`, `metadata`.
  - [ ] `id` must be deterministic from provider id and external session id.
  - [ ] `metadata` must include detected CLI version when available.
  - [ ] `metadata` may include project hash, source file path, source database name, parse version, and safe provider metadata.
  - [ ] `metadata` must not include conversation text.
- [ ] Implement the `token_usage_history` table.
  - [ ] Required PLAN fields: `session_id`, `timestamp`, `input_tokens`, `output_tokens`, `cached_tokens`, `reasoning_tokens`, `thoughts_tokens`, `tool_tokens`, `total_tokens`, `raw_data`.
  - [ ] Add generic V1 fields: `id`, `provider_id`, `external_event_id`, `model_name`, `source`, `created_at`.
  - [ ] `external_event_id` must make repeated syncs idempotent.
  - [ ] Add a unique constraint that prevents duplicate token usage rows for the same provider/session/event.
- [ ] Implement safe database access.
  - [ ] Use write transactions for each provider sync batch.
  - [ ] Enable WAL mode.
  - [ ] Use UTC ISO timestamps.
  - [ ] Validate JSON before storing it.
  - [ ] Provide read queries used by the API without exposing raw secret-bearing metadata.

### 3. Provider Contract And Normalization

- [ ] Define one provider contract used by all providers.
  - [ ] Each provider exposes metadata: id, display name, default home path, supported active probe, supported passive sync.
  - [ ] Each provider can run a full passive scan.
  - [ ] Each provider can run an incremental passive scan from stored high-water marks.
  - [ ] Each provider can run an active quota probe if enabled and credentials are available.
  - [ ] Each provider returns normalized records, not database writes.
- [ ] Define normalized session records.
  - [ ] Required fields: provider id, external session id, model name, project path, project name, created at, last seen at, metadata.
  - [ ] Missing model name must be stored as `unknown`.
  - [ ] Missing project path must be stored as `null`, not guessed.
- [ ] Define normalized token usage records.
  - [ ] Required fields: provider id, external session id, external event id, timestamp, model name, token counts, raw metadata.
  - [ ] All absent token counts must become `0`.
  - [ ] `total_tokens` must be provider-provided when available; otherwise compute from known token fields.
- [ ] Define normalized quota records.
  - [ ] Required fields: provider id, quota name, timestamp, used percent, remaining percent, window minutes, resets at, source, raw metadata.
  - [ ] If only remaining percent is known, compute used percent as `100 - remaining_percent`.
  - [ ] If only used percent is known, compute remaining percent as `100 - used_percent`.
  - [ ] Clamp computed percentages to the `[0, 100]` range.
- [ ] Define high-water mark rules.
  - [ ] File-based sources track path, size, mtime, and last processed offset or last event timestamp.
  - [ ] SQLite sources track database path and last processed row id or timestamp.
  - [ ] Active probes track last successful probe timestamp per provider and quota name.
  - [ ] Store high-water marks in provider `config` JSON or a generic sync-state JSON field. Do not create provider-specific tables.

### 4. Gemini Provider

- [ ] Implement Gemini passive history syncing.
  - [ ] Discover supported chat JSON and JSONL files under the configured Gemini home.
  - [ ] Parse session metadata: session id, kind, project hash, start time, last updated.
  - [ ] Parse Gemini message token data without storing message text.
  - [ ] Deduplicate token-bearing messages using a stable event identity.
  - [ ] Normalize each chat file into sessions and token usage rows.
  - [ ] Store project hash and detected safe metadata in `sessions.metadata`.
- [ ] Implement Gemini incremental syncing.
  - [ ] Skip unchanged files using high-water marks.
  - [ ] Re-read changed files and rely on deterministic event ids to avoid duplicate rows.
  - [ ] Update high-water marks only after a successful transaction.
- [ ] Implement Gemini active quota probing.
  - [ ] Read OAuth credentials from the configured Gemini home.
  - [ ] Refresh expired access tokens in memory.
  - [ ] Call Code Assist `loadCodeAssist`.
  - [ ] Call Code Assist `retrieveUserQuota`.
  - [ ] Store each returned bucket as a quota history row.
  - [ ] Use quota names that include model id and token type in raw metadata while keeping `quota_name` generic and queryable.
- [ ] Implement Gemini error handling.
  - [ ] If credentials are missing, record a provider health warning and keep passive syncing operational.
  - [ ] If quota probing fails, do not fail the whole daemon loop.
  - [ ] Interactive fallback is optional for manual CLI mode only and must not block daemon execution.

### 5. Codex Provider

- [ ] Implement Codex passive session syncing.
  - [ ] Discover `sessions/**/*.jsonl`.
  - [ ] Include `archived_sessions/*.jsonl` unless disabled in config.
  - [ ] Parse session metadata from `session_meta` and `turn_context`.
  - [ ] Parse `token_count` events.
  - [ ] Normalize latest total usage when available.
  - [ ] Store CLI version in `sessions.metadata` when present.
- [ ] Implement Codex local SQLite syncing.
  - [ ] Read `state_5.sqlite` in read-only mode.
  - [ ] Read `logs_2.sqlite` in read-only mode.
  - [ ] Extract useful session, thread, model, token, and rate-limit metadata without mutating provider databases.
  - [ ] Convert local SQLite data into the common schema.
  - [ ] Use deterministic event ids to avoid duplicate token rows.
- [ ] Implement Codex quota extraction.
  - [ ] Extract primary and secondary rate limit windows from session files when available.
  - [ ] Convert each window to a quota history row with `quota_name` `primary` or `secondary`.
  - [ ] Store reset timestamp and window minutes.
- [ ] Implement Codex WHAM active probing.
  - [ ] Read the local access token from `auth.json` in memory.
  - [ ] Call the WHAM usage endpoint only when active probing is enabled.
  - [ ] Normalize returned quota metadata into quota history rows.
  - [ ] Store only safe usage metadata.
- [ ] Implement Codex resilience.
  - [ ] Missing auth disables active probe only.
  - [ ] Missing local SQLite databases must not disable session JSONL parsing.
  - [ ] Broken JSONL lines must be counted as parse failures and skipped.

### 6. Copilot Provider

- [ ] Implement Copilot passive session syncing.
  - [ ] Discover `session-state/**/events.jsonl`.
  - [ ] Parse `session.start`, `session.model_change`, `assistant.message`, and `session.shutdown` usage metadata.
  - [ ] Prefer `session.shutdown` model metrics as authoritative session totals when present.
  - [ ] Normalize per-model usage into token usage rows.
  - [ ] Store models seen and safe CLI metadata in `sessions.metadata`.
- [ ] Implement Copilot precise weekly active probing.
  - [ ] Read the local Copilot token from `config.json` in memory.
  - [ ] Resolve the API base URL through `https://api.github.com/copilot_internal/user`.
  - [ ] Send one minimal chat completion request using the locked probe model from the current R&D script unless tests override it.
  - [ ] Parse response headers with prefixes `x-usage-ratelimit-` and `x-quota-snapshot-`.
  - [ ] For `x-usage-ratelimit-weekly`, parse query params `ent`, `ov`, `ovPerm`, `rem`, `rst`, `hasQuota`, `tbb`, and `totRem` when present.
  - [ ] Store weekly `remaining_percent = rem`.
  - [ ] Store weekly `used_percent = 100 - rem`.
  - [ ] Store weekly `resets_at = rst`.
  - [ ] Store `quota_name = weekly` and `source = active_probe`.
- [ ] Implement Copilot session and snapshot quotas.
  - [ ] Parse `x-usage-ratelimit-session` into `quota_name = session`.
  - [ ] Parse `x-quota-snapshot-chat` into `quota_name = chat`.
  - [ ] Parse `x-quota-snapshot-completions` into `quota_name = completions`.
  - [ ] Parse `x-quota-snapshot-premium_interactions` into `quota_name = premium_interactions`.
- [ ] Implement Copilot monthly entitlement probing.
  - [ ] Keep the monthly entitlement probe separate from the weekly header probe.
  - [ ] Use GitHub cookie discovery only when explicitly enabled or already configured safely.
  - [ ] Store monthly/premium request quota with `quota_name = monthly` or `premium_interactions`.
  - [ ] Do not use entitlement data to estimate weekly usage.
- [ ] Implement Copilot safety.
  - [ ] Never persist the local Copilot token.
  - [ ] Never persist raw cookies.
  - [ ] Never persist unsanitized command history.
  - [ ] Mark the active weekly probe in UI/API as an active request that may consume quota.

### 7. Daemon And Sync Scheduler

- [ ] Implement daemon lifecycle.
  - [ ] `quota-tracker daemon` starts the scheduler and the API server in one process.
  - [ ] The daemon applies migrations before starting work.
  - [ ] The daemon creates default provider rows if missing.
  - [ ] The daemon logs startup config without secrets.
- [ ] Implement initial full scan.
  - [ ] On first run, perform a full passive scan for every enabled provider.
  - [ ] When a provider is enabled for the first time, perform a full passive scan for that provider.
  - [ ] Store high-water marks only after successful writes.
- [ ] Implement incremental passive syncing.
  - [ ] Poll enabled providers every configured passive sync interval.
  - [ ] Process only changed files or new source rows when high-water marks allow it.
  - [ ] Preserve idempotency through deterministic ids and database constraints.
- [ ] Implement active quota probing.
  - [ ] Poll enabled providers every configured active probe interval.
  - [ ] Skip providers whose active probe is disabled.
  - [ ] Do not run active probes more frequently than configured.
  - [ ] Record failed probes as health state without inserting bogus quota rows.
- [ ] Implement resilience.
  - [ ] Restarting the daemon must not duplicate sessions or token usage rows.
  - [ ] Disabling a provider stops future scans but keeps historical rows.
  - [ ] Re-enabling a provider resumes from high-water marks unless the user explicitly requests a full rescan.
  - [ ] Provider failures must not crash the whole daemon loop.
- [ ] Implement manual operations.
  - [ ] Manual scan endpoint and CLI command trigger passive sync for a provider or all providers.
  - [ ] Manual probe endpoint and CLI command trigger active quota probing for a provider or all providers.
  - [ ] Manual full rescan resets the selected provider high-water marks only after user confirmation in CLI or explicit API payload.

### 8. CLI Contract

- [ ] Implement `quota-tracker config show`.
  - [ ] Prints sanitized config JSON.
  - [ ] Does not print secrets.
- [ ] Implement `quota-tracker config set`.
  - [ ] Supports setting provider enabled flags, home paths, active probe intervals, passive sync intervals, host, port, database path, and log level.
  - [ ] Validates paths and intervals before writing config.
- [ ] Implement `quota-tracker migrate`.
  - [ ] Applies migrations and exits.
  - [ ] Is safe to run repeatedly.
- [ ] Implement `quota-tracker scan`.
  - [ ] Supports `--provider all|gemini|codex|copilot`.
  - [ ] Supports `--full` to ignore high-water marks after explicit invocation.
  - [ ] Prints a concise summary: sessions upserted, token rows inserted, quota rows inserted, parse failures.
- [ ] Implement `quota-tracker probe`.
  - [ ] Supports `--provider all|gemini|codex|copilot`.
  - [ ] Supports `--dry-run` where possible by using mocked or cached probe responses, not live network calls.
  - [ ] Prints quota name, used percent, remaining percent, reset time, and source.
- [ ] Implement `quota-tracker serve`.
  - [ ] Starts the FastAPI server and serves the React build.
  - [ ] Uses configured host and port unless CLI flags override them.
- [ ] Implement `quota-tracker daemon`.
  - [ ] Starts API server and scheduler in one process.
  - [ ] Uses one user-facing port.
  - [ ] Handles SIGTERM and SIGINT cleanly.

### 9. Single-Port API And Web Serving

- [ ] Implement FastAPI application startup.
  - [ ] Apply migrations.
  - [ ] Load config.
  - [ ] Initialize provider registry.
  - [ ] Initialize scheduler only for daemon mode.
- [ ] Implement API endpoints.
  - [ ] `GET /api/health` returns service status, database status, scheduler status, and provider health summaries.
  - [ ] `GET /api/providers` returns provider configs and health summaries without secrets.
  - [ ] `PATCH /api/providers/{id}` enables/disables a provider and updates safe provider config.
  - [ ] `POST /api/providers/{id}/scan` triggers passive sync.
  - [ ] `POST /api/providers/{id}/probe` triggers active quota probe.
  - [ ] `GET /api/quotas` returns quota history filtered by provider id, quota name, time range, and limit.
  - [ ] `GET /api/sessions` returns sessions filtered by provider id, project name, model name, and time range.
  - [ ] `GET /api/token-usage` returns aggregated token usage grouped by provider, model, project, session, day, or hour.
  - [ ] `GET /api/config` returns sanitized config.
  - [ ] `PATCH /api/config` updates global config and validates intervals, host, port, and paths.
- [ ] Implement static frontend serving.
  - [ ] Serve `/` from the built React assets.
  - [ ] Serve frontend asset files from the same FastAPI process.
  - [ ] Return `index.html` for non-API frontend routes.
  - [ ] Never proxy to a separate frontend dev server in production.
- [ ] Implement API response rules.
  - [ ] Return UTC ISO timestamps.
  - [ ] Return percentages as numbers, not formatted strings.
  - [ ] Return token counts as integers.
  - [ ] Return no secrets.
  - [ ] Return stable JSON shapes tested by snapshots.

### 10. React Dashboard

- [ ] Implement frontend application shell.
  - [ ] Use React TypeScript.
  - [ ] Use relative API calls only.
  - [ ] Support loading, empty, error, and stale-data states.
  - [ ] Do not display conversation content.
- [ ] Implement global overview.
  - [ ] Show enabled providers.
  - [ ] Show latest quota state per provider and quota name.
  - [ ] Show total tokens over selectable time ranges.
  - [ ] Show token breakdown by provider and model.
  - [ ] Use ECharts for quota and usage visualizations.
- [ ] Implement provider drill-down.
  - [ ] Show provider health.
  - [ ] Show provider-specific latest quota rows through normalized fields.
  - [ ] Show sessions table with project, model, created time, last seen time, and token totals.
  - [ ] Show token usage charts grouped by model and time.
- [ ] Implement configuration panel.
  - [ ] Toggle providers enabled/disabled.
  - [ ] Edit provider home paths.
  - [ ] Edit active probe intervals and passive sync intervals.
  - [ ] Trigger manual scan.
  - [ ] Trigger manual active quota probe.
  - [ ] Show warning text before active probes that can consume provider quota.
- [ ] Implement frontend production behavior.
  - [ ] Build assets are served by FastAPI.
  - [ ] No runtime dependency on Vite.
  - [ ] The browser uses the same origin for UI and API.

### 11. Installer And Systemd Setup

- [ ] Implement one-liner install flow.
  - [ ] Support `curl -sSL <install-url> | sh`.
  - [ ] Install into a deterministic user-level location.
  - [ ] Create config, data, and log directories if missing.
  - [ ] Do not overwrite user config without merging known fields.
- [ ] Implement interactive configuration.
  - [ ] Auto-detect Gemini, Codex, and Copilot homes.
  - [ ] Ask whether to enable all detected providers or select a subset.
  - [ ] Allow non-standard provider paths.
  - [ ] Allow configuring host, port, active probe interval, and passive sync interval.
- [ ] Implement idempotent reconfiguration.
  - [ ] Re-running the installer updates existing config without duplicating provider entries.
  - [ ] Re-running the installer updates the systemd user unit if content changed.
  - [ ] Re-running the installer preserves database contents.
- [ ] Implement systemd user service.
  - [ ] Service name: `quota-tracker.service`.
  - [ ] Command runs `quota-tracker daemon`.
  - [ ] Restart policy handles daemon failures.
  - [ ] Logs go to journald and the configured log directory.
  - [ ] Installer enables and starts the service when the user confirms.

### 12. Performance And Data Minimization

- [ ] Keep the daemon lightweight.
  - [ ] Poll on configurable intervals, not tight loops.
  - [ ] Use file mtimes, sizes, offsets, timestamps, and row ids to avoid unnecessary full scans.
  - [ ] Use SQLite indexes for dashboard queries.
  - [ ] Avoid loading all historical records into memory for API aggregations.
- [ ] Keep storage lean.
  - [ ] Store normalized metrics and safe metadata only.
  - [ ] Do not store raw chat messages.
  - [ ] Do not store prompt or assistant text.
  - [ ] Do not store raw command history.
  - [ ] Do not store provider secret material.
- [ ] Make scan behavior observable.
  - [ ] Track last successful scan time per provider.
  - [ ] Track last successful active probe time per provider.
  - [ ] Track parse failure counts.
  - [ ] Expose provider health through `/api/health` and the dashboard.

## API, CLI, Database, And Config Contracts

### Runtime Modes

- [ ] `quota-tracker daemon` is the normal installed mode.
- [ ] `quota-tracker serve` is for serving the API and frontend without background polling.
- [ ] `quota-tracker scan` is for one-off passive sync.
- [ ] `quota-tracker probe` is for one-off active quota probing.
- [ ] `quota-tracker migrate` is for one-off schema migration.

### API Contract

- [ ] All API paths start with `/api/`.
- [ ] All API responses are JSON.
- [ ] Percentages are numeric values from `0` to `100`.
- [ ] Unknown percentages are `null`.
- [ ] All timestamps are UTC ISO 8601 strings or `null`.
- [ ] Provider ids are exactly `gemini`, `codex`, and `copilot`.
- [ ] API must return sanitized metadata only.

### Database Contract

- [ ] The only provider data tables are `providers`, `quota_history`, `sessions`, and `token_usage_history`.
- [ ] Internal technical tables are allowed only for migrations and generic sync state.
- [ ] No provider-specific tables are allowed.
- [ ] Provider-specific details go into JSON metadata fields after sanitization.
- [ ] Session ids and external event ids must make repeated scans idempotent.

### Config Contract

- [ ] Config is JSON.
- [ ] Config is human-readable and stable across installer re-runs.
- [ ] Config contains no secrets.
- [ ] Config supports non-standard provider homes.
- [ ] Config supports provider enable/disable.
- [ ] Config supports polling controls.
- [ ] Config supports host and port.
- [ ] Config supports database path.

## Testing Strategy

The testing strategy is part of the implementation. Do not leave it for later.

### Test Layout

- [ ] Create `tests/unit/` for pure parsing, normalization, config, migration, and utility tests.
- [ ] Create `tests/integration/` for provider snapshot tests, database sync tests, API tests, and daemon scheduler tests.
- [ ] Create `tests/snapshots/` with version-stamped provider fixtures.
- [ ] Create `tests/snapshots/<provider>/<cli-version>/input/` for sample local provider files.
- [ ] Create `tests/snapshots/<provider>/<cli-version>/expected.json` for normalized expected output.
- [ ] Create `tests/fixtures/` for shared HTTP responses, quota headers, sanitized config files, and tiny SQLite databases.

### Version-Stamped Snapshot Testing

- [ ] Snapshot directories must encode provider and CLI version.
  - [ ] Example: `tests/snapshots/gemini/0.35.0/`.
  - [ ] Example: `tests/snapshots/gemini/0.40.1/`.
  - [ ] Example: `tests/snapshots/codex/<version>/`.
  - [ ] Example: `tests/snapshots/copilot/1.0.40/`.
- [ ] Each snapshot must contain realistic sample config/session/log files generated by or modeled after that CLI version.
- [ ] Each snapshot must contain `expected.json`.
- [ ] `expected.json` must include:
  - normalized sessions
  - normalized token usage
  - normalized quota rows when fixture data contains quota information
  - expected detected CLI version in `sessions.metadata`
  - expected parse failure counts when fixture files intentionally contain bad records
- [ ] `pytest` must iterate through all snapshot directories automatically.
- [ ] Snapshot tests must fail when a provider parser changes normalized output unexpectedly.
- [ ] Snapshot tests must not contain real secrets or real conversation content.

### Nix-Powered Multi-Version Testing

- [ ] Extend the Nix flake to expose checks for provider parser tests.
- [ ] Add Nix matrix shells or flake checks for pinned provider CLI versions where packages are available.
- [ ] The Nix test matrix must at minimum run snapshot tests against the committed fixtures.
- [ ] Where pinned CLIs are available, generate or validate fixtures under the matching CLI version environment.
- [ ] `nix flake check` must run the repository quality checks and provider integration tests.
- [ ] The matrix must verify:
  - parser compatibility across supported CLI versions
  - accurate token extraction
  - accurate quota extraction
  - correct provider CLI version detection stored in `sessions.metadata`

### Unit Tests

- [ ] Test config defaults and config merge behavior.
- [ ] Test config sanitization.
- [ ] Test SQLite migrations are idempotent.
- [ ] Test provider normalization maps all provider token fields to common fields.
- [ ] Test percentage computation from used and remaining values.
- [ ] Test UTC timestamp normalization.
- [ ] Test deterministic session ids and external event ids.
- [ ] Test secret redaction for tokens, cookies, authorization headers, and command history.
- [ ] Test Copilot quota header parsing with exact `x-usage-ratelimit-weekly` fixture values.
- [ ] Test Gemini Code Assist bucket normalization.
- [ ] Test Codex primary and secondary rate limit normalization.

### Integration Tests

- [ ] Test full scan inserts normalized providers, sessions, token rows, and quota rows.
- [ ] Test second scan against unchanged fixtures inserts no duplicates.
- [ ] Test incremental scan after fixture modification inserts only new events.
- [ ] Test provider disable stops scans without deleting historical data.
- [ ] Test provider re-enable resumes from high-water marks.
- [ ] Test manual full rescan remains idempotent through deterministic ids.
- [ ] Test API endpoints against a populated test database.
- [ ] Test frontend build artifacts are served by FastAPI.
- [ ] Test `/api/...` routes are not swallowed by frontend route fallback.
- [ ] Test daemon shutdown on SIGTERM does not corrupt SQLite state.

### Active Probe Tests

- [ ] Active network calls must be mocked in automated tests.
- [ ] No automated test may require real Gemini, Codex, Copilot, GitHub, Google, or OpenAI credentials.
- [ ] Provide fixture HTTP responses for:
  - Gemini `loadCodeAssist`
  - Gemini `retrieveUserQuota`
  - Codex WHAM usage
  - Copilot `copilot_internal/user`
  - Copilot chat completion headers
  - Copilot entitlement response
- [ ] Manual live probe tests may exist only behind an explicit marker such as `pytest -m live`.
- [ ] Live tests must be skipped by default.

### Frontend Tests

- [ ] Test TypeScript compilation.
- [ ] Test API client uses relative URLs only.
- [ ] Test overview renders provider and quota data from mocked API responses.
- [ ] Test provider drill-down renders sessions and token charts from mocked API responses.
- [ ] Test configuration panel sends correct PATCH/POST requests.
- [ ] Test active probe warning appears before triggering probe actions.

### Installer Tests

- [ ] Test installer creates config, data, and log directories.
- [ ] Test installer detects provider homes from fixture home directories.
- [ ] Test installer writes a user-level systemd unit.
- [ ] Test running installer twice does not duplicate config entries.
- [ ] Test running installer twice preserves existing custom paths and intervals.
- [ ] Test systemd unit content is updated when the installed command path changes.

### Required Quality Gates

- [ ] `ruff check .`
- [ ] `ruff format --check .`
- [ ] `mypy .`
- [ ] `interrogate -v .`
- [ ] `pytest`
- [ ] `nix flake check`
- [ ] Python code target: 100% test coverage.
- [ ] Python docstring target: 100% interrogate coverage.
- [ ] Any temporary exception to 100% coverage or docstring coverage must be documented in the roadmap issue or PR and removed before V1 completion.
- [ ] Each quality gate must have a dedicated `Taskfile.yml` task.
- [ ] `task validate` must combine all quality gates and must be the default command for local pre-commit validation.
- [ ] `task validate:quiet` must combine the same quality gates with silent success and limited failure output.
- [ ] CI and documentation must use the same task names so local and CI validation cannot drift.

## PLAN.md Coverage Checklist

Use this checklist to verify that every feature from `PLAN.md` is represented in implementation tasks.

- [ ] Lightweight Linux daemon.
- [ ] Tracks AI provider quotas.
- [ ] Tracks session history.
- [ ] Supports Gemini.
- [ ] Supports Codex.
- [ ] Supports Copilot.
- [ ] Stores data in structured SQLite.
- [ ] Uses normalized storage common to all providers.
- [ ] Enables local auditing.
- [ ] Enables visualization through a React dashboard.
- [ ] Uses Python 3.11+ requirement from PLAN.md, implemented as Python 3.12+.
- [ ] Uses SQLite.
- [ ] Uses a lightweight Python web server, locked to FastAPI.
- [ ] Serves API and React build from one backend.
- [ ] Uses React TypeScript.
- [ ] Uses ECharts.
- [ ] Uses `ruff` format and check.
- [ ] Uses strict `mypy`.
- [ ] Uses `interrogate` with 100% docstring coverage target.
- [ ] Uses `pytest` with 100% code coverage target.
- [ ] Provides a root `Taskfile.yml` that enumerates development, build, run, test, install, and validation commands.
- [ ] Provides `task validate:quiet` for silent-success validation with limited failure output.
- [ ] Includes Nix-powered integration and multi-version testing.
- [ ] Includes Nix matrix shells or flake checks for pinned provider CLI versions where available.
- [ ] Includes version-stamped snapshots.
- [ ] Includes sample config and session data in snapshots.
- [ ] Includes `expected.json` benchmark outputs.
- [ ] Makes `pytest` iterate through version snapshots.
- [ ] Verifies token extraction against snapshots.
- [ ] Verifies quota extraction against snapshots.
- [ ] Verifies CLI version detection in `sessions.metadata`.
- [ ] Integrates checks into `nix flake check`.
- [ ] Provides one-liner install path.
- [ ] Makes install idempotent.
- [ ] Supports interactive provider selection.
- [ ] Auto-detects available providers.
- [ ] Supports reconfiguration by re-running installer.
- [ ] Supports adding providers after first install.
- [ ] Supports removing or disabling providers after first install.
- [ ] Automatically configures or updates a user-level `systemd` unit.
- [ ] Performs active quota probing.
- [ ] Performs passive history syncing.
- [ ] Runs initial full scan on first run.
- [ ] Runs initial full scan when a new provider is added.
- [ ] Uses high-water marks for incremental updates.
- [ ] Handles daemon restarts without data duplication.
- [ ] Handles provider toggles without data corruption.
- [ ] Normalizes provider data before storage.
- [ ] Uses no provider-specific data tables.
- [ ] Provides global overview across all providers.
- [ ] Provides individual provider drill-down.
- [ ] Provides configuration panel.
- [ ] Lets users enable and disable providers.
- [ ] Lets users trigger rescans.
- [ ] Lets users customize provider paths.
- [ ] Lets users configure polling intervals.
- [ ] Keeps RAM and CPU footprint minimal.
- [ ] Uses lean storage.
- [ ] Stores no session content.
- [ ] Implements `providers` table.
- [ ] Implements `quota_history` table.
- [ ] Implements `sessions` table.
- [ ] Implements `token_usage_history` table.
- [ ] Uses JSON blobs for extensible config, metadata, and raw provider quota data.

## Definition Of Done

- [ ] The application runs with `quota-tracker daemon` and exposes one user-facing port.
- [ ] Opening `http://127.0.0.1:8787/` shows the React dashboard.
- [ ] The dashboard calls the backend with relative `/api/...` URLs.
- [ ] `GET /api/health` reports database, scheduler, and provider state.
- [ ] A first run creates the database, provider rows, and default config.
- [ ] A full scan populates sessions and token usage from local provider fixtures.
- [ ] Active probes populate quota history when mocked credentials/responses are provided.
- [ ] Copilot weekly quota uses `x-usage-ratelimit-weekly`, not entitlement estimation.
- [ ] Re-running scans does not duplicate rows.
- [ ] Disabling a provider stops future polling and keeps historical data.
- [ ] Installer can be run twice without duplicating config or systemd entries.
- [ ] No test fixture, log, API response, or database row contains real secrets.
- [ ] No database table stores conversation content.
- [ ] All required quality gates pass:
  - [ ] `ruff check .`
  - [ ] `ruff format --check .`
  - [ ] `mypy .`
  - [ ] `interrogate -v .`
  - [ ] `pytest`
  - [ ] `nix flake check`
- [ ] `Taskfile.yml` exists at the repository root and lists every supported developer command.
- [ ] `task validate` runs every required validation gate.
- [ ] `task validate:quiet` runs every required validation gate, produces no output on success except an optional one-line summary, and limits failure output to the first 120 captured lines plus the full log path.
