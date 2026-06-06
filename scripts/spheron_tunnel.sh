#!/usr/bin/env bash
# SSH tunnel to studio (3000) and API (8001). Reads .env.spheron from repo root.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$REPO_ROOT/.env.spheron"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE — run: make spheron-set-ip IP=<vm-ip>"
  exit 1
fi
# shellcheck disable=SC1090
source "$ENV_FILE"

: "${SPHERON_IP:?SPHERON_IP not set in .env.spheron}"
: "${SPHERON_USER:=root}"
KEY="${SPHERON_SSH_KEY:-$HOME/.ssh/id_ed25519}"

echo "Tunnel → http://127.0.0.1:3000 (web)  http://127.0.0.1:8001/health (api)"
echo "Host: ${SPHERON_USER}@${SPHERON_IP}"
exec ssh -i "$KEY" -o StrictHostKeyChecking=accept-new \
  -L 3000:127.0.0.1:3000 \
  -L 8001:127.0.0.1:8001 \
  "${SPHERON_USER}@${SPHERON_IP}"
