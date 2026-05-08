# quota-tracker

A daemon to track AI provider quotas and session history.

## Development

This project uses `task` (go-task) as the canonical command registry.

### Setup

```bash
task setup
```

### Quality Gates

```bash
task format
task lint
task typecheck
task docstrings
task test
task validate
task validate:quiet
```

### Running

```bash
task run-daemon
task run-api
task scan
task probe
task migrate
```

## Audit Scripts (Legacy/R&D)

The original audit scripts are available for reference:
- `codex_local_audit.py`
- `gemini_local_audit.py`
- `copilot_local_audit.py`
- `get_weekly_quota.py`
