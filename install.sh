#!/usr/bin/env bash
# quota-tracker — installer & updater
# curl -fsSL https://raw.githubusercontent.com/Thomas97460/quota-tracker/main/install.sh | bash
set -euo pipefail
IFS=$'\n\t'

# ── Color palette ──────────────────────────────────────────────────────────────
if [[ -t 1 ]] && [[ -z "${NO_COLOR:-}" ]]; then
  R='\033[0m'; BOLD='\033[1m'; DIM='\033[2m'
  CYAN='\033[38;5;44m'; VIOLET='\033[38;5;141m'
  GREEN='\033[38;5;76m'; AMBER='\033[38;5;214m'; RED='\033[38;5;196m'
else
  R=''; BOLD=''; DIM=''; CYAN=''; VIOLET=''; GREEN=''; AMBER=''; RED=''
fi
IS_TTY=0; [[ -t 1 ]] && IS_TTY=1

# ── Runtime config (override with env vars) ────────────────────────────────────
REPO_SLUG="${REPO_SLUG:-Thomas97460/quota-tracker}"
VERSION="${VERSION:-latest}"
INSTALL_SOURCE="${INSTALL_SOURCE:-auto}"   # auto | release | local
INTERACTIVE="${INTERACTIVE:-auto}"         # auto | 1 | 0
AUTO_SCAN="${AUTO_SCAN:-1}"
FULL_RESCAN="${FULL_RESCAN:-1}"
RUN_PROBE="${RUN_PROBE:-0}"                # live probe consumes API quota
RESTART_SERVICE="${RESTART_SERVICE:-1}"

TARGET_BIN_DIR="${HOME}/.local/bin"
TARGET_BIN="${TARGET_BIN_DIR}/quota-tracker"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

# ── Architecture ───────────────────────────────────────────────────────────────
ARCH="$(uname -m)"
case "${ARCH}" in
  x86_64)        ASSET_ARCH="amd64" ;;
  aarch64|arm64) ASSET_ARCH="arm64" ;;
  *) printf >&2 "\n  \033[38;5;196m✖\033[0m  unsupported architecture: %s\n\n" "${ARCH}"; exit 1 ;;
esac
ASSET_NAME="quota-tracker-linux-${ASSET_ARCH}"

if [[ "${VERSION}" == "latest" ]]; then
  BASE_URL="https://github.com/${REPO_SLUG}/releases/latest/download"
  _resolved="$(curl -fsSL --max-time 5 "https://api.github.com/repos/${REPO_SLUG}/releases/latest" \
    2>/dev/null | grep '"tag_name"' | grep -oE 'v[0-9]+\.[0-9]+\.[0-9]+' | head -1 || true)"
  if [[ -z "${_resolved}" ]]; then
    # GitHub unreachable — fall back to latest local git tag
    _resolved="$(git -C "$(dirname "$0")" tag --list 'v*' --sort=-version:refname 2>/dev/null | head -1 || true)"
  fi
  [[ -n "${_resolved}" ]] && VERSION="${_resolved}"
else
  BASE_URL="https://github.com/${REPO_SLUG}/releases/download/${VERSION}"
fi

# ── Helpers ────────────────────────────────────────────────────────────────────
command_exists()           { command -v "$1" >/dev/null 2>&1; }
local_checkout_available() { [[ -f "pyproject.toml" && -d "quota_tracker" && -f "quota_tracker/cli.py" ]]; }
systemctl_user()           { command_exists systemctl && systemctl --user "$@" >/dev/null 2>&1; }

# ── Output primitives ──────────────────────────────────────────────────────────
ok()      { printf "    ${GREEN}✔${R}  %s\n" "$1"; }
info()    { printf "    ${DIM}·${R}  %s\n" "$1"; }
warn()    { printf "    ${AMBER}⚠${R}  %s\n" "$1"; }
die()     { spin_stop; printf "\n    ${RED}✖${R}  ${BOLD}%s${R}\n\n" "$1" >&2; exit 1; }
section() { printf "\n  ${CYAN}${BOLD}%s${R}${DIM} ─────────────────────────────────────${R}\n" "$1"; }

# ── Spinner ────────────────────────────────────────────────────────────────────
_SPIN_PID=""

spin_start() {
  [[ "${IS_TTY}" -eq 0 ]] && { printf "    · %s\n" "$1"; return; }
  ( i=0
    while true; do
      case $(( i % 10 )) in
        0) f='⠋';; 1) f='⠙';; 2) f='⠹';; 3) f='⠸';; 4) f='⠼';;
        5) f='⠴';; 6) f='⠦';; 7) f='⠧';; 8) f='⠇';; *) f='⠏';;
      esac
      printf "\r    ${CYAN}%s${R}  %s " "${f}" "$1"
      sleep 0.08
      i=$(( i + 1 ))
    done ) &
  _SPIN_PID=$!
}

spin_stop() {
  [[ -z "${_SPIN_PID}" ]] && return
  kill "${_SPIN_PID}" 2>/dev/null || true
  wait "${_SPIN_PID}" 2>/dev/null || true
  _SPIN_PID=""
  [[ "${IS_TTY}" -eq 1 ]] && printf "\r\033[2K"
}

# ── Error trap ─────────────────────────────────────────────────────────────────
_LAST_OP="(unknown)"
trap 'spin_stop; die "failed at: ${_LAST_OP}"' ERR

# ── Dashboard URL ──────────────────────────────────────────────────────────────
get_dashboard_url() {
  local cfg="${HOME}/.config/quota-tracker/config.json"
  if [[ -f "${cfg}" ]] && command_exists python3; then
    python3 -c "
import json, sys
try:
    d = json.loads(open('${cfg}').read())
    h = d.get('daemon', {}).get('web_host', '127.0.0.1')
    p = d.get('daemon', {}).get('web_port', 8787)
    print('http://{}:{}'.format(h, p))
except Exception:
    print('http://127.0.0.1:8787')
" 2>/dev/null
  else
    printf "http://127.0.0.1:8787\n"
  fi
}

# ── Mode detection ─────────────────────────────────────────────────────────────
MODE="install"
PREV_VERSION=""
if [[ -x "${TARGET_BIN}" ]] || command_exists quota-tracker 2>/dev/null; then
  MODE="update"
  PREV_VERSION="$("${TARGET_BIN}" --version 2>/dev/null | awk '{print $2}' || echo '')"
  # Already up to date → config mode (reconfigure only, no artifact)
  if [[ -n "${PREV_VERSION}" && "${PREV_VERSION}" == "${VERSION#v}" ]]; then
    MODE="config"
  fi
fi

# ── Banner ─────────────────────────────────────────────────────────────────────
print_banner() {
  if [[ "${IS_TTY}" -eq 1 ]] && [[ -z "${NO_COLOR:-}" ]] && [[ "${COLORTERM:-}" =~ ^(truecolor|24bit)$ ]]; then
    WM="\033[38;2;0;215;215mq\033[38;2;43;202;225mu\033[38;2;65;196;230mo\033[38;2;87;189;235mt\033[38;2;109;182;240ma\033[38;2;131;176;245m-\033[38;2;153;169;250mt\033[38;2;164;158;253mr\033[38;2;168;152;254ma\033[38;2;172;147;255mc\033[38;2;175;140;255mk\033[38;2;175;137;255me\033[38;2;175;135;255mr\033[0m"
    GM="\033[38;2;0;215;215m▰\033[38;2;19;206;219m▰\033[38;2;39;197;224m▰\033[38;2;58;188;228m▰\033[38;2;78;179;233m▰\033[38;2;97;170;237m▰\033[38;2;117;161;242m▰\033[38;2;136;152;246m▰\033[38;2;156;143;251m▰\033[38;2;175;135;255m▰\033[0m"
    GMR="\033[38;2;175;135;255m▰\033[38;2;156;143;251m▰\033[38;2;136;152;246m▰\033[38;2;117;161;242m▰\033[38;2;97;170;237m▰\033[38;2;78;179;233m▰\033[38;2;58;188;228m▰\033[38;2;39;197;224m▰\033[38;2;19;206;219m▰\033[38;2;0;215;215m▰\033[0m"
  elif [[ "${IS_TTY}" -eq 1 ]] && [[ -z "${NO_COLOR:-}" ]]; then
    WM="${CYAN}q${VIOLET}u${CYAN}o${VIOLET}t${CYAN}a${VIOLET}-${CYAN}t${VIOLET}r${CYAN}a${VIOLET}c${CYAN}k${VIOLET}e${CYAN}r${R}"
    GM="${CYAN}▰${VIOLET}▰${CYAN}▰${VIOLET}▰${CYAN}▰${VIOLET}▰${CYAN}▰${VIOLET}▰${CYAN}▰${VIOLET}▰${R}"
    GMR="${VIOLET}▰${CYAN}▰${VIOLET}▰${CYAN}▰${VIOLET}▰${CYAN}▰${VIOLET}▰${CYAN}▰${VIOLET}▰${CYAN}▰${R}"
  else
    WM="quota-tracker"; GM="▰▰▰▰▰▰▰▰▰▰"; GMR="▰▰▰▰▰▰▰▰▰▰"
  fi

  local mode_color="${GREEN}"
  [[ "${MODE}" == "update" ]] && mode_color="${AMBER}"
  [[ "${MODE}" == "config"  ]] && mode_color="${CYAN}"

  printf '\n'
  printf "  ${BOLD}${GM}  ${WM}  ${GMR}${R}\n"
  printf "  ${CYAN}════════════════════════════════════════${R}\n"
  printf "  ${DIM}local-first quota & token observability${R}\n"
  if [[ "${MODE}" == "update" && -n "${PREV_VERSION}" ]]; then
    printf "  ${DIM}mode${R}  ${CYAN}›${R}  ${mode_color}${BOLD}%s${R}  ${DIM}│  v%s → %s  │  linux/%s${R}\n" \
      "${MODE}" "${PREV_VERSION}" "${VERSION}" "${ASSET_ARCH}"
  elif [[ "${MODE}" == "config" ]]; then
    printf "  ${DIM}mode${R}  ${CYAN}›${R}  ${mode_color}${BOLD}%s${R}  ${DIM}│  v%s (up to date)  │  linux/%s${R}\n" \
      "${MODE}" "${PREV_VERSION}" "${ASSET_ARCH}"
  else
    printf "  ${DIM}mode${R}  ${CYAN}›${R}  ${mode_color}${BOLD}%s${R}  ${DIM}│  %s  │  linux/%s${R}\n" \
      "${MODE}" "${VERSION}" "${ASSET_ARCH}"
  fi
  printf '\n'
}

# ── Ready box ──────────────────────────────────────────────────────────────────
print_ready() {
  local url="$1"
  local url_len="${#url}"
  # Inner width = 52 (number of ─ in SEP)
  # Prefix "   open your dashboard  ›  " = 27 visible chars
  local pad=$(( 52 - 27 - url_len ))
  [[ "${pad}" -lt 1 ]] && pad=1
  # "   ✔  quota-tracker is ready" = 28 visible chars → trailing = 52 - 28 = 24
  local SEP="────────────────────────────────────────────────────"

  printf '\n'
  printf "  ${CYAN}${BOLD}╭%s╮${R}\n" "${SEP}"
  printf "  ${CYAN}${BOLD}│${R}%52s${CYAN}${BOLD}│${R}\n" ''
  printf "  ${CYAN}${BOLD}│${R}   ${GREEN}${BOLD}✔  quota-tracker is ready${R}%24s${CYAN}${BOLD}│${R}\n" ''
  printf "  ${CYAN}${BOLD}│${R}%52s${CYAN}${BOLD}│${R}\n" ''
  printf "  ${CYAN}${BOLD}│${R}   ${DIM}open your dashboard${R}  ${CYAN}›${R}  ${BOLD}%s${R}%*s${CYAN}${BOLD}│${R}\n" "${url}" "${pad}" ''
  printf "  ${CYAN}${BOLD}│${R}%52s${CYAN}${BOLD}│${R}\n" ''
  printf "  ${CYAN}${BOLD}╰%s╯${R}\n" "${SEP}"
  printf '\n'
}

# ══════════════════════════════════════════════════════════════════════════════
print_banner

# ── artifact ───────────────────────────────────────────────────────────────────
if [[ "${MODE}" == "config" ]]; then
  section "artifact"
  info "already on v${PREV_VERSION} — skipping build/download"
else

if [[ "${INSTALL_SOURCE}" == "auto" ]]; then
  if local_checkout_available; then
    INSTALL_SOURCE="local"
  else
    INSTALL_SOURCE="release"
  fi
fi

case "${INSTALL_SOURCE}" in
  local)
    local_checkout_available || die "INSTALL_SOURCE=local requires running from the repository root"
    command_exists uv  || die "uv is required for local builds (https://docs.astral.sh/uv)"
    command_exists npm || die "npm is required for local frontend builds"
    info "building from local checkout"
    _LAST_OP="build frontend"
    spin_start "building frontend"
    if [[ -f "frontend/package-lock.json" ]]; then
      npm --prefix frontend ci   >/dev/null 2>&1
    else
      npm --prefix frontend install >/dev/null 2>&1
    fi
    npm --prefix frontend run build >/dev/null 2>&1
    spin_stop
    _LAST_OP="build binary"
    spin_start "compiling binary"
    uv sync --extra dev >/dev/null 2>&1
    env -u PYTHONPATH uv run pyinstaller \
      --noconfirm --onefile --name quota-tracker \
      --add-data "frontend/dist:frontend/dist" \
      quota_tracker/cli.py >/dev/null 2>&1
    spin_stop
    cp "dist/quota-tracker" "${TMP_DIR}/${ASSET_NAME}"
    ( cd "${TMP_DIR}" && sha256sum "${ASSET_NAME}" > "${ASSET_NAME}.sha256" )
    ok "built from source  (linux/${ASSET_ARCH})"
    ;;
  release)
    info "release channel  ›  ${REPO_SLUG}"
    _LAST_OP="download release"
    spin_start "downloading"
    curl -fsSL "${BASE_URL}/${ASSET_NAME}"        -o "${TMP_DIR}/${ASSET_NAME}"
    curl -fsSL "${BASE_URL}/${ASSET_NAME}.sha256" -o "${TMP_DIR}/${ASSET_NAME}.sha256"
    spin_stop
    ok "downloaded  ${ASSET_NAME}"
    ;;
  *)
    die "INSTALL_SOURCE must be auto, release, or local"
    ;;
esac

_LAST_OP="verify checksum"
( cd "${TMP_DIR}" && sha256sum -c "${ASSET_NAME}.sha256" --quiet ) \
  || die "checksum mismatch — download may be corrupt"
ok "checksum verified"
fi  # end of [[ MODE != config ]] block

# ── binary ─────────────────────────────────────────────────────────────────────
section "binary"
if [[ "${MODE}" == "config" ]]; then
  info "binary unchanged  →  ${TARGET_BIN}"
else
  _LAST_OP="install binary"
  mkdir -p "${TARGET_BIN_DIR}"
  install -Dm755 "${TMP_DIR}/${ASSET_NAME}" "${TARGET_BIN}"
  mkdir -p \
    "${HOME}/.config/quota-tracker" \
    "${HOME}/.local/share/quota-tracker" \
    "${HOME}/.local/state/quota-tracker/logs"
  NEW_VERSION="$(quota-tracker --version 2>/dev/null | awk '{print $2}' || echo '?')"
  ok "installed v${NEW_VERSION}  →  ${TARGET_BIN}"
fi
export PATH="${TARGET_BIN_DIR}:${PATH}"

# ── configure ──────────────────────────────────────────────────────────────────
section "configure"
_LAST_OP="configure"
CONFIG_PATH="$(quota-tracker config-path)"
if [[ "${INTERACTIVE}" == "auto" ]]; then
  [[ -f "${CONFIG_PATH}" ]] && INTERACTIVE="0" || INTERACTIVE="1"
fi

if [[ "${INTERACTIVE}" == "1" ]]; then
  printf '\n'
  quota-tracker install --interactive --exec-path "${TARGET_BIN}"
  printf '\n'
else
  while IFS= read -r line; do
    [[ -n "${line}" ]] && ok "${line}"
  done < <(quota-tracker install --exec-path "${TARGET_BIN}" 2>/dev/null)
fi

# ── database ───────────────────────────────────────────────────────────────────
section "database"
_LAST_OP="apply migrations"
MIGRATE_OUT="$(quota-tracker migrate 2>/dev/null)"
ok "${MIGRATE_OUT}"

# ── stop service before backfill to avoid SQLite write contention ──────────────
_LAST_OP="stop service"
if systemctl_user is-active --quiet quota-tracker.service 2>/dev/null; then
  systemctl --user stop quota-tracker.service >/dev/null 2>&1 || true
  info "service stopped for backfill"
fi

# ── backfill ───────────────────────────────────────────────────────────────────
section "backfill"
_LAST_OP="local scan"
if [[ "${AUTO_SCAN}" == "1" ]]; then
  SCAN_FLAGS="--provider all"
  [[ "${FULL_RESCAN}" == "1" ]] && SCAN_FLAGS="${SCAN_FLAGS} --full"
  spin_start "scanning local usage data"
  # shellcheck disable=SC2086
  SCAN_OUT="$(quota-tracker scan ${SCAN_FLAGS} 2>/dev/null)" || { spin_stop; warn "scan failed — skipping backfill (run manually: quota-tracker scan --provider all --full)"; SCAN_OUT=""; }
  spin_stop
  if [[ -n "${SCAN_OUT}" ]]; then
    SESSIONS="$(printf '%s' "${SCAN_OUT}" | grep -oE 'sessions_upserted=[0-9]+' | grep -oE '[0-9]+' || true)"
    TOKENS="$(printf '%s'   "${SCAN_OUT}" | grep -oE 'token_rows_inserted=[0-9]+' | grep -oE '[0-9]+' || true)"
    FAILURES="$(printf '%s' "${SCAN_OUT}" | grep -oE 'parse_failures=[0-9]+' | grep -oE '[0-9]+' || true)"
    SESSIONS="${SESSIONS:-0}"; TOKENS="${TOKENS:-0}"; FAILURES="${FAILURES:-0}"
    ok "$(printf '%s sessions, %s token events indexed' "${SESSIONS}" "${TOKENS}")"
    [[ "${FAILURES}" -gt 0 ]] && warn "${FAILURES} parse failure(s) — run with FULL_RESCAN=1 to retry"
  fi
else
  info "skipped  (set AUTO_SCAN=1 to index local history)"
fi

_LAST_OP="active probe"
if [[ "${RUN_PROBE}" == "1" ]]; then
  spin_start "probing live quotas"
  quota-tracker probe --provider all >/dev/null 2>&1
  spin_stop
  ok "live quota probe complete"
else
  info "live probe skipped  (set RUN_PROBE=1 to activate)"
fi

# ── service ────────────────────────────────────────────────────────────────────
section "service"
_LAST_OP="install service"
while IFS= read -r line; do
  [[ -n "${line}" ]] && ok "${line}"
done < <(quota-tracker install-user-service --exec-path "${TARGET_BIN}" 2>/dev/null)

if [[ "${RESTART_SERVICE}" == "1" ]]; then
  _LAST_OP="restart service"
  if systemctl_user daemon-reload; then
    systemctl_user restart quota-tracker.service \
      || warn "service restart failed — check: systemctl --user status quota-tracker.service"
    ok "quota-tracker.service restarted"
  else
    warn "systemd user session unavailable — service file written but not started"
    info "start manually: systemctl --user start quota-tracker.service"
  fi
else
  info "restart skipped  (set RESTART_SERVICE=1 to auto-start)"
fi

if systemctl_user is-active --quiet quota-tracker.service 2>/dev/null; then
  ok "quota-tracker.service is active"
fi

# ── done ───────────────────────────────────────────────────────────────────────
DASHBOARD_URL="$(get_dashboard_url)"
print_ready "${DASHBOARD_URL}"
