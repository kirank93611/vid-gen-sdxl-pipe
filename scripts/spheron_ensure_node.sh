#!/usr/bin/env bash
# Install Node 20 via nvm (no sudo). Must be sourced: . scripts/spheron_ensure_node.sh
set -euo pipefail

export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"

_spheron_load_nvm() {
  if [[ -s "$NVM_DIR/nvm.sh" ]]; then
    # shellcheck disable=SC1091
    . "$NVM_DIR/nvm.sh"
  fi
}

if command -v npm >/dev/null 2>&1; then
  echo "Node OK: $(node -v) $(npm -v)"
elif _spheron_load_nvm && command -v npm >/dev/null 2>&1; then
  echo "Node OK: $(node -v) $(npm -v)"
else
  echo "==> Installing nvm + Node 20 (user-local, no sudo)..."
  if [[ ! -s "$NVM_DIR/nvm.sh" ]]; then
    curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash
  fi
  _spheron_load_nvm
  nvm install 20
  nvm use 20
  echo "Node installed: $(node -v) $(npm -v)"
fi
