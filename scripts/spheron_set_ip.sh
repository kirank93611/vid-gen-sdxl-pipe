#!/usr/bin/env bash
# Write .env.spheron and drop stale known_hosts entry for the IP.
# Usage: SPM_USER=ubuntu bash scripts/spheron_set_ip.sh <ip>
set -euo pipefail

IP="${1:?Usage: $0 <ip>}"
USER="${SPM_USER:-ubuntu}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$REPO_ROOT/.env.spheron"
SSH_KEY="${SPHERON_SSH_KEY:-$HOME/.ssh/id_ed25519}"
if [[ "$USER" == "root" ]]; then
  SPHERON_DIR="/root/image-sd"
else
  SPHERON_DIR="/home/${USER}/image-sd"
fi

cat >"$ENV_FILE" <<EOF
# Updated $(date -u +%Y-%m-%dT%H:%MZ) — spot VMs get a new IP each deploy
SPHERON_IP=${IP}
SPHERON_USER=${USER}
SPHERON_DIR=${SPHERON_DIR}
SPHERON_SSH_KEY=${SSH_KEY}
EOF

ssh-keygen -R "$IP" 2>/dev/null || true
echo "Wrote $ENV_FILE"
echo "  SPHERON_HOST=${USER}@${IP}"
echo "Next: make spheron-up   (sync + fast bootstrap on VM)"
