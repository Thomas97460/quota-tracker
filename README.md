# quota-tracker

Application quota-tracker (daemon/API/CLI) avec scripts d'audit conservés comme références.

## Commandes (Taskfile)

Utiliser `task` depuis la racine du dépôt.

```bash
task setup
task format
task lint
task typecheck
task docstrings
task test
task test-unit
task test-integration
task test-snapshots
task test-frontend
task build-frontend
task nix-check
task validate
task validate:quiet
task run-api
task run-daemon
task scan
task probe
task migrate
task install-user-service
task clean
```

## Scripts de référence conservés

- `codex_local_audit.py`
- `gemini_local_audit.py`
- `copilot_local_audit.py`
- `get_weekly_quota.py`

Ces scripts restent disponibles tant que les comportements de production équivalents ne sont pas totalement implémentés et testés dans le package `quota_tracker`.
