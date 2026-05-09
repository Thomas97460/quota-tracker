#!/usr/bin/env bash
# quota-tracker installer — curl | bash
# Usage: curl -fsSL https://raw.githubusercontent.com/collet/quota-tracker/main/install.sh | bash
set -euo pipefail

# ── Color palette ─────────────────────────────────────────────────────────────
# keep in sync with quota_tracker/_ui.py:BANNER_LINES
if [[ -t 1 ]] && [[ -z "${NO_COLOR:-}" ]]; then
  R='\033[0m'
  BOLD='\033[1m'
  DIM='\033[2m'
  CYAN='\033[38;5;44m'
  VIOLET='\033[38;5;141m'
  GREEN='\033[38;5;76m'
  AMBER='\033[38;5;214m'
  RED='\033[38;5;196m'
else
  R='' BOLD='' DIM='' CYAN='' VIOLET='' GREEN='' AMBER='' RED=''
fi

# ── Brand banner ──────────────────────────────────────────────────────────────
# keep in sync with quota_tracker/_ui.py:BANNER_LINES
# Wordmark gradient: 5 color stops from cyan (0,215,215) → violet (175,135,255)
# Gauge: 10 filled segments (▰) matching the final frame of the Python animation.
# Truecolor gate: emit 24-bit stops when COLORTERM is truecolor/24bit;
#   otherwise fall back to alternating 256-color cyan/violet.
print_banner() {
  printf '\n'
  if [[ -t 1 ]] && [[ -z "${NO_COLOR:-}" ]] && [[ "${COLORTERM:-}" =~ ^(truecolor|24bit)$ ]]; then
    # 24-bit gradient wordmark — 5 evenly-spaced color stops across 13 chars
    # stop0 (0,215,215)  stop1 (43,202,225)  stop2 (87,189,235)
    # stop3 (131,176,245) stop4 (175,135,255)
    WM="\033[38;2;0;215;215mq\033[38;2;43;202;225mu\033[38;2;65;196;230mo\033[38;2;87;189;235mt\033[38;2;109;182;240ma\033[38;2;131;176;245m-\033[38;2;153;169;250mt\033[38;2;164;158;253mr\033[38;2;168;152;254ma\033[38;2;172;147;255mc\033[38;2;175;140;255mk\033[38;2;175;137;255me\033[38;2;175;135;255mr\033[0m"
    GM="\033[38;2;0;215;215m▰\033[38;2;19;206;219m▰\033[38;2;39;197;224m▰\033[38;2;58;188;228m▰\033[38;2;78;179;233m▰\033[38;2;97;170;237m▰\033[38;2;117;161;242m▰\033[38;2;136;152;246m▰\033[38;2;156;143;251m▰\033[38;2;175;135;255m▰\033[0m"
    printf "  ${BOLD}${GM}  ${WM}${R}\n"
  elif [[ -t 1 ]] && [[ -z "${NO_COLOR:-}" ]]; then
    # 256-color fallback: alternate cyan/violet per character on wordmark
    WM="${CYAN}q${VIOLET}u${CYAN}o${VIOLET}t${CYAN}a${VIOLET}-${CYAN}t${VIOLET}r${CYAN}a${VIOLET}c${CYAN}k${VIOLET}e${CYAN}r${R}"
    GM="${CYAN}▰${VIOLET}▰${CYAN}▰${VIOLET}▰${CYAN}▰${VIOLET}▰${CYAN}▰${VIOLET}▰${CYAN}▰${VIOLET}▰${R}"
    printf "  ${BOLD}${GM}  ${WM}${R}\n"
  else
    printf "  ▰▰▰▰▰▰▰▰▰▰  quota-tracker\n"
  fi
  printf "  ${CYAN}════════════════════════════════════════${R}\n"
  printf "  ${DIM}local-first quota & token observability${R}\n"
  printf '\n'
}

# ── Step helpers ───────────────────────────────────────────────────────────────
_STEP_CURRENT=0
_STEP_TOTAL=8

step() {
  _STEP_CURRENT=$(( _STEP_CURRENT + 1 ))
  printf "\n${CYAN}⟶${R} ${BOLD}[${_STEP_CURRENT}/${_STEP_TOTAL}]${R} %s\n" "$1"
}

ok() {
  printf "    ${GREEN}✔${R}  %s\n" "$1"
}

warn() {
  printf "    ${AMBER}⚠${R}  %s\n" "$1"
}

die() {
  printf "\n    ${RED}✖${R}  ${BOLD}install failed${R}: %s\n" "$1" >&2
  exit 1
}

# ── Error trap ────────────────────────────────────────────────────────────────
_LAST_STEP="(unknown step)"
trap 'die "failed during: ${_LAST_STEP}"' ERR

# ── Config ────────────────────────────────────────────────────────────────────
REPO_SLUG="${REPO_SLUG:-collet/quota-tracker}"
VERSION="${VERSION:-latest}"
INSTALL_SOURCE="${INSTALL_SOURCE:-auto}"   # auto | release | local
INTERACTIVE="${INTERACTIVE:-auto}"         # auto | 1 | 0
AUTO_SCAN="${AUTO_SCAN:-1}"
FULL_RESCAN="${FULL_RESCAN:-1}"
RUN_PROBE="${RUN_PROBE:-0}"                # active probes can consume provider quota
RESTART_SERVICE="${RESTART_SERVICE:-1}"
TARGET_BIN_DIR="${HOME}/.local/bin"
TARGET_BIN="${TARGET_BIN_DIR}/quota-tracker"
ASSET_NAME="quota-tracker-linux-amd64"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

if [[ "${VERSION}" == "latest" ]]; then
  BASE_URL="https://github.com/${REPO_SLUG}/releases/latest/download"
else
  BASE_URL="https://github.com/${REPO_SLUG}/releases/download/${VERSION}"
fi

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

systemctl_user() {
  if ! command_exists systemctl; then
    return 1
  fi
  systemctl --user "$@" >/dev/null 2>&1
}

local_checkout_available() {
  [[ -f "pyproject.toml" && -d "quota_tracker" && -f "quota_tracker/cli.py" ]]
}

# ── Install ───────────────────────────────────────────────────────────────────
print_banner

# [1/8] Prepare artifact
_LAST_STEP="Prepare artifact"
step "Prepare artifact"
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
    command_exists uv || die "uv is required for local builds"
    command_exists npm || die "npm is required for local frontend builds"
    printf "    ${DIM}building from local checkout: %s${R}\n" "$(pwd)"
    uv sync --extra dev
    if [[ -f "frontend/package-lock.json" ]]; then
      npm --prefix frontend ci
    else
      npm --prefix frontend install
    fi
    npm --prefix frontend run build
    env -u PYTHONPATH uv run pyinstaller \
      --noconfirm \
      --onefile \
      --name quota-tracker \
      --add-data "frontend/dist:frontend/dist" \
      quota_tracker/cli.py
    cp "dist/quota-tracker" "${TMP_DIR}/${ASSET_NAME}"
    (cd "${TMP_DIR}" && sha256sum "${ASSET_NAME}" > "${ASSET_NAME}.sha256")
    ok "Built local ${ASSET_NAME}"
    ;;
  release)
    printf "    ${DIM}from %s${R}\n" "${BASE_URL}"
    curl -fsSL "${BASE_URL}/${ASSET_NAME}" -o "${TMP_DIR}/${ASSET_NAME}"
    curl -fsSL "${BASE_URL}/${ASSET_NAME}.sha256" -o "${TMP_DIR}/${ASSET_NAME}.sha256"
    ok "Downloaded ${ASSET_NAME}"
    ;;
  *)
    die "INSTALL_SOURCE must be auto, release, or local"
    ;;
esac

# [2/8] Verify checksum
_LAST_STEP="Verify checksum"
step "Verify checksum"
(
  cd "${TMP_DIR}"
  sha256sum -c "${ASSET_NAME}.sha256" --quiet
)
ok "Checksum verified"

# [3/8] Install binary
_LAST_STEP="Install binary"
step "Install binary"
mkdir -p "${TARGET_BIN_DIR}"
install -Dm755 "${TMP_DIR}/${ASSET_NAME}" "${TARGET_BIN}"

mkdir -p "${HOME}/.config/quota-tracker"
mkdir -p "${HOME}/.local/share/quota-tracker"
mkdir -p "${HOME}/.local/state/quota-tracker/logs"

ok "Installed to ${TARGET_BIN}"

# Make sure the binary is on PATH for the rest of this script
export PATH="${TARGET_BIN_DIR}:${PATH}"

# [4/8] Configure application
_LAST_STEP="Configure application"
step "Configure application"
CONFIG_PATH="$(quota-tracker config-path)"
if [[ "${INTERACTIVE}" == "auto" ]]; then
  if [[ -f "${CONFIG_PATH}" ]]; then
    INTERACTIVE="0"
  else
    INTERACTIVE="1"
  fi
fi
if [[ "${INTERACTIVE}" == "1" ]]; then
  printf "    ${DIM}Running interactive installer …${R}\n"
  quota-tracker install --interactive --exec-path "${TARGET_BIN}"
else
  printf "    ${DIM}Existing config detected; refreshing service config non-interactively …${R}\n"
  quota-tracker install --exec-path "${TARGET_BIN}"
fi
printf '\n'

# [5/8] Migrate database
_LAST_STEP="Migrate database"
step "Migrate database"
printf "    ${DIM}Applying database migrations …${R}\n"
quota-tracker migrate
ok "Database migrated"

# [6/8] Backfill local usage
_LAST_STEP="Backfill local usage"
step "Backfill local usage"
if [[ "${AUTO_SCAN}" == "1" ]]; then
  if [[ "${FULL_RESCAN}" == "1" ]]; then
    quota-tracker scan --provider all --full
    ok "Full local usage scan completed"
  else
    quota-tracker scan --provider all
    ok "Incremental local usage scan completed"
  fi
else
  warn "AUTO_SCAN=0; skipped local usage backfill"
fi
if [[ "${RUN_PROBE}" == "1" ]]; then
  quota-tracker probe --provider all
  ok "Active quota probe completed"
else
  warn "Skipped active quota probe by default; set RUN_PROBE=1 to refresh live quotas"
fi

# [7/8] Install and restart service
_LAST_STEP="Install & restart service"
step "Install & restart service"
quota-tracker install-user-service --exec-path "${TARGET_BIN}"
ok "Service installed and enabled"
if [[ "${RESTART_SERVICE}" == "1" ]]; then
  if systemctl_user daemon-reload; then
    systemctl_user restart quota-tracker.service || warn "Could not restart user service"
    ok "Service restart requested"
  else
    warn "systemd user session unavailable; service file was still written"
  fi
else
  warn "RESTART_SERVICE=0; skipped service restart"
fi

# [8/8] Health check
_LAST_STEP="Health check"
step "Health check"
if systemctl_user is-active --quiet quota-tracker.service; then
  ok "quota-tracker.service is active"
else
  warn "Service is not active yet; inspect with: systemctl --user status quota-tracker.service"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
printf '\n'
printf "  ${GREEN}${BOLD}Installation complete.${R}\n"
printf "  ${DIM}Check status:${R}  systemctl --user status quota-tracker.service\n"
WEB_PORT="$(quota-tracker config show | sed -n 's/.*"web_port": \\([0-9][0-9]*\\).*/\\1/p' | head -1)"
printf "  ${DIM}Open UI:${R}       http://127.0.0.1:${WEB_PORT:-8787}\n"
printf '\n'
