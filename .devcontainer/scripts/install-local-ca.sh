#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CERT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)/certs"
TARGET_DIR="/usr/local/share/ca-certificates/custom"

if [[ ! -d "$CERT_DIR" ]]; then
  echo "[install-local-ca] No cert directory found at $CERT_DIR. Skipping."
  exit 0
fi

shopt -s nullglob
cert_files=("$CERT_DIR"/*.crt "$CERT_DIR"/*.pem)

if [[ ${#cert_files[@]} -eq 0 ]]; then
  echo "[install-local-ca] No .crt or .pem files found in $CERT_DIR. Skipping."
  exit 0
fi

sudo mkdir -p "$TARGET_DIR"
sudo find "$TARGET_DIR" -type f -name '*.crt' -delete

for cert_file in "${cert_files[@]}"; do
  cert_name="$(basename "$cert_file")"
  cert_stem="${cert_name%.*}"
  sudo cp "$cert_file" "$TARGET_DIR/$cert_stem.crt"
done

sudo update-ca-certificates

echo "[install-local-ca] Installed ${#cert_files[@]} certificate(s)."
