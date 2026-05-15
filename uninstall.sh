#!/usr/bin/env bash
# quota-tracker — local uninstall helper
set -euo pipefail
IFS=$'\n\t'

APP_NAME="quota-tracker"
SERVICE_NAME="quota-tracker.service"
BIN_PATH="${HOME}/.local/bin/${APP_NAME}"
CONFIG_DIR="${HOME}/.config/${APP_NAME}"
CONFIG_PATH="${CONFIG_DIR}/config.json"
DATA_DIR="${HOME}/.local/share/${APP_NAME}"
STATE_DIR="${HOME}/.local/state/${APP_NAME}"
DEFAULT_DB_PATH="${DATA_DIR}/${APP_NAME}.sqlite3"
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
section() { printf "\n  ${CYAN}${BOLD}%s${R}${DIM} ─────────────────────────────────────${R}\n" "$1"; }

confirm() {
  local question="$1"
  local answer=""
  while true; do
    if [[ -t 0 ]]; then
      printf "    %s [y/n]: " "${question}"
      if ! read -r answer; then
        printf "\n"
        warn "could not read confirmation; please enter y or n."
        continue
      fi
    elif [[ -t 1 && -r /dev/tty ]]; then
      printf "    %s [y/n]: " "${question}" >/dev/tty
      if ! read -r answer </dev/tty 2>/dev/null; then
        printf "\n" >/dev/tty
        warn "could not read /dev/tty; please enter y or n."
        continue
      fi
    else
      warn "no interactive terminal; defaulting to no for safety: ${question}"
      return 1
    fi

    case "${answer}" in
      y|Y|yes|YES|Yes|o|O|oui|OUI|Oui) return 0 ;;
      n|N|no|NO|No|non|NON|Non) return 1 ;;
      *) warn "invalid input; please enter 'y' for yes or 'n' for no." ;;
    esac
  done
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
printf "  ${DIM}removes the user daemon, app files, and optionally the local database${R}\n"

DB_PATH="$(db_path_from_config)"

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

section "files"
info "binary: ${BIN_PATH}"
info "config: ${CONFIG_DIR}"
info "state/logs: ${STATE_DIR}"
if [[ -e "${BIN_PATH}" || -e "${CONFIG_DIR}" || -e "${STATE_DIR}" ]]; then
  if confirm "Delete installed app files except the database?"; then
    rm -f "${BIN_PATH}"
    rm -rf "${CONFIG_DIR}" "${STATE_DIR}"
    ok "installed app files removed"
  else
    info "installed app files left unchanged"
  fi
else
  info "installed app files already absent"
fi

section "database"
info "database: ${DB_PATH}"
info "data dir: ${DATA_DIR}"
if [[ -e "${DB_PATH}" || -e "${DB_PATH}-wal" || -e "${DB_PATH}-shm" || -d "${DATA_DIR}" ]]; then
  if confirm "Delete the quota-tracker SQLite database and data directory?"; then
    rm -f "${DB_PATH}" "${DB_PATH}-wal" "${DB_PATH}-shm"
    rm -rf "${DATA_DIR}"
    ok "database and data directory removed"
  else
    info "database left unchanged"
  fi
else
  info "database files already absent"
fi

printf '\n'
ok "uninstall helper finished"
