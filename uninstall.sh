#!/usr/bin/env bash
# quota-tracker — local daemon/database uninstall helper
set -euo pipefail
IFS=$'\n\t'

APP_NAME="quota-tracker"
SERVICE_NAME="quota-tracker.service"
CONFIG_PATH="${HOME}/.config/${APP_NAME}/config.json"
DEFAULT_DB_PATH="${HOME}/.local/share/${APP_NAME}/${APP_NAME}.sqlite3"
UNIT_PATH="${HOME}/.config/systemd/user/${SERVICE_NAME}"

if [[ -t 1 ]] && [[ -z "${NO_COLOR:-}" ]]; then
  R='\033[0m'; BOLD='\033[1m'; DIM='\033[2m'
  CYAN='\033[38;5;44m'; GREEN='\033[38;5;76m'; AMBER='\033[38;5;214m'; RED='\033[38;5;196m'
else
  R=''; BOLD=''; DIM=''; CYAN=''; GREEN=''; AMBER=''; RED=''
fi

command_exists() { command -v "$1" >/dev/null 2>&1; }
systemctl_user() { command_exists systemctl && systemctl --user "$@" >/dev/null 2>&1; }

info() { printf "    ${DIM}·${R}  %s\n" "$1"; }
ok() { printf "    ${GREEN}✔${R}  %s\n" "$1"; }
warn() { printf "    ${AMBER}⚠${R}  %s\n" "$1"; }
err() { printf "    ${RED}✖${R}  %s\n" "$1" >&2; }
section() { printf "\n  ${CYAN}${BOLD}%s${R}${DIM} ─────────────────────────────────────${R}\n" "$1"; }

confirm() {
  local question="$1"
  local answer=""
  if [[ -t 0 ]]; then
    if ! read -r -p "    ${question} [y/N]: " answer; then
      warn "could not read confirmation; defaulting to no for: ${question}"
      return 1
    fi
  elif [[ -t 1 && -r /dev/tty ]]; then
    if ! read -r -p "    ${question} [y/N]: " answer </dev/tty 2>/dev/null; then
      warn "could not read /dev/tty; defaulting to no for: ${question}"
      return 1
    fi
  else
    warn "no interactive terminal; defaulting to no for: ${question}"
    return 1
  fi
  case "${answer}" in
    y|Y|yes|YES|Yes|o|O|oui|OUI|Oui) return 0 ;;
    *) return 1 ;;
  esac
}

db_path_from_config() {
  if [[ -f "${CONFIG_PATH}" ]] && command_exists python3; then
    python3 - "${CONFIG_PATH}" "${DEFAULT_DB_PATH}" <<'PY'
import json
import sys
from pathlib import Path

config_path = Path(sys.argv[1])
default = sys.argv[2]
try:
    data = json.loads(config_path.read_text())
    print(data.get("daemon", {}).get("database_path") or default)
except Exception:
    print(default)
PY
  else
    printf '%s\n' "${DEFAULT_DB_PATH}"
  fi
}

printf '\n'
printf "  ${BOLD}quota-tracker uninstall${R}\n"
printf "  ${CYAN}════════════════════════════════════════${R}\n"
printf "  ${DIM}removes the user daemon and optionally the local database${R}\n"

section "daemon"
if [[ -f "${UNIT_PATH}" ]] || systemctl_user list-unit-files "${SERVICE_NAME}"; then
  info "service: ${SERVICE_NAME}"
  info "unit: ${UNIT_PATH}"
  if confirm "Uninstall the quota-tracker user daemon?"; then
    if systemctl_user is-active --quiet "${SERVICE_NAME}"; then
      systemctl --user stop "${SERVICE_NAME}" >/dev/null 2>&1 || warn "failed to stop ${SERVICE_NAME}"
    fi
    if systemctl_user is-enabled --quiet "${SERVICE_NAME}"; then
      systemctl --user disable "${SERVICE_NAME}" >/dev/null 2>&1 || warn "failed to disable ${SERVICE_NAME}"
    fi
    if [[ -f "${UNIT_PATH}" ]]; then
      rm -f "${UNIT_PATH}"
      ok "removed ${UNIT_PATH}"
    else
      info "unit file already absent"
    fi
    if systemctl_user daemon-reload; then
      systemctl --user reset-failed "${SERVICE_NAME}" >/dev/null 2>&1 || true
      ok "systemd user daemon reloaded"
    else
      warn "systemd user session unavailable; skipped daemon-reload"
    fi
  else
    info "daemon left unchanged"
  fi
else
  info "no ${SERVICE_NAME} user unit found"
fi

section "database"
DB_PATH="$(db_path_from_config)"
info "database: ${DB_PATH}"
if [[ -e "${DB_PATH}" || -e "${DB_PATH}-wal" || -e "${DB_PATH}-shm" ]]; then
  if confirm "Delete the quota-tracker SQLite database?"; then
    rm -f "${DB_PATH}" "${DB_PATH}-wal" "${DB_PATH}-shm"
    ok "database files removed"
  else
    info "database left unchanged"
  fi
else
  info "database files already absent"
fi

printf '\n'
ok "uninstall helper finished"
