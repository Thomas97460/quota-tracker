#!/usr/bin/env bash
set -euo pipefail

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

echo "[quota-tracker] Downloading release asset from ${BASE_URL} ..."
curl -fsSL "${BASE_URL}/${ASSET_NAME}" -o "${TMP_DIR}/${ASSET_NAME}"
curl -fsSL "${BASE_URL}/${ASSET_NAME}.sha256" -o "${TMP_DIR}/${ASSET_NAME}.sha256"

echo "[quota-tracker] Verifying checksum..."
(
  cd "${TMP_DIR}"
  sha256sum -c "${ASSET_NAME}.sha256"
)

mkdir -p "${TARGET_BIN_DIR}"
install -Dm755 "${TMP_DIR}/${ASSET_NAME}" "${TARGET_BIN}"

mkdir -p "${HOME}/.config/quota-tracker"
mkdir -p "${HOME}/.local/share/quota-tracker"
mkdir -p "${HOME}/.local/state/quota-tracker/logs"

export PATH="${TARGET_BIN_DIR}:${PATH}"

echo "[quota-tracker] Running interactive installer..."
quota-tracker install --interactive

echo "[quota-tracker] Installing and enabling user service..."
quota-tracker install-user-service

echo "[quota-tracker] Done."
echo "Service status: systemctl --user status quota-tracker.service"
