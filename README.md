# quota-tracker

Scripts Python pour auditer localement Codex (`~/.codex`) et Gemini (`~/.gemini`).

## Codex

Fichier : [`codex_local_audit.py`](/home/collet/Bureau/quota-tracker/codex_local_audit.py)

```bash
uv run --python 3.12 python codex_local_audit.py
uv run --python 3.12 python codex_local_audit.py --json
uv run --python 3.12 python codex_local_audit.py --json --output codex_audit_report.json
```

Ce script remonte notamment : config, auth sanitisée, tokens détaillés, plages de dates, quota restant en `%` (si présent via `rate_limits`), et stats SQLite.

## Gemini

Fichier : [`gemini_local_audit.py`](/home/collet/Bureau/quota-tracker/gemini_local_audit.py)

```bash
uv run --python 3.12 python gemini_local_audit.py
uv run --python 3.12 python gemini_local_audit.py --json
uv run --python 3.12 python gemini_local_audit.py --json --output gemini_audit_report.json
uv run --python 3.12 python gemini_local_audit.py --quota-timeout 30
```

Le script Gemini remonte : settings/projets/auth sanitisée, tokens détaillés depuis `~/.gemini/tmp/**/chats`, plages de dates, top sessions, et le quota live Gemini Code Assist via l'endpoint interne `retrieveUserQuota` utilisé par la CLI. Si cet appel échoue, il tente un fallback via la CLI Gemini (`/stats model` en mode interactif automatisé).

La sonde Code Assist utilise `~/.gemini/oauth_creds.json` mais n'affiche jamais les tokens. Elle retourne seulement le projet Code Assist, le tier et les buckets de quota par modèle (`remaining_percent`, `used_percent`, `reset_time`).
