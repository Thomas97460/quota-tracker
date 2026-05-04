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

Le script Gemini remonte : settings/projets/auth sanitisée, tokens détaillés depuis `~/.gemini/tmp/**/chats`, plages de dates, top sessions, et tente systématiquement de récupérer le quota live via la CLI Gemini (`/stats model` en mode interactif automatisé).
