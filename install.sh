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
_STEP_TOTAL=4

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

# ── Install ───────────────────────────────────────────────────────────────────
print_banner

# [1/4] Download release
_LAST_STEP="Download release"
step "Download release"
printf "    ${DIM}from %s${R}\n" "${BASE_URL}"
curl -fsSL "${BASE_URL}/${ASSET_NAME}" -o "${TMP_DIR}/${ASSET_NAME}"
curl -fsSL "${BASE_URL}/${ASSET_NAME}.sha256" -o "${TMP_DIR}/${ASSET_NAME}.sha256"
ok "Downloaded ${ASSET_NAME}"

# [2/4] Verify checksum
_LAST_STEP="Verify checksum"
step "Verify checksum"
(
  cd "${TMP_DIR}"
  sha256sum -c "${ASSET_NAME}.sha256" --quiet
)
ok "Checksum verified"

# [3/4] Install binary
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

# [4/4] Configure and enable service
_LAST_STEP="Configure & enable service"
step "Configure & enable service"
printf "    ${DIM}Running interactive installer …${R}\n"
quota-tracker install --interactive
printf '\n'
quota-tracker install-user-service
ok "Service installed and enabled"

# ── Done ──────────────────────────────────────────────────────────────────────
printf '\n'
printf "  ${GREEN}${BOLD}Installation complete.${R}\n"
printf "  ${DIM}Check status:${R}  systemctl --user status quota-tracker.service\n"
printf '\n'
