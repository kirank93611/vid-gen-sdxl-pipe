#!/usr/bin/env bash
# Clean production build + start Next.js on VM. Fixes stale HTML / 500 on /_next/static/*.
# Run on VM:  cd ~/image-sd && bash scripts/spheron_deploy_web.sh
# Sync code from Mac first: make spheron-sync  (from Mac only)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WEB_DIR="$REPO_ROOT/apps/web"
cd "$WEB_DIR"

stop_port_3000() {
  echo "==> Freeing port 3000..."
  pkill -9 -f "next dev" 2>/dev/null || true
  pkill -9 -f "next start" 2>/dev/null || true
  pkill -9 -f "next-server" 2>/dev/null || true
  if command -v fuser >/dev/null 2>&1; then
    fuser -k 3000/tcp 2>/dev/null || true
  fi
  if command -v lsof >/dev/null 2>&1; then
    local pids
    pids="$(lsof -ti :3000 2>/dev/null || true)"
    if [[ -n "$pids" ]]; then
      kill -9 $pids 2>/dev/null || true
    fi
  fi
  sleep 3
  if ss -tln 2>/dev/null | grep -q ':3000 '; then
    echo "ERROR: port 3000 still in use. Run: ss -tlnp | grep 3000"
    ss -tlnp 2>/dev/null | grep 3000 || true
    exit 1
  fi
}

stop_port_3000

echo "==> Removing stale .next..."
rm -rf .next

cat > .env.local <<EOF
SDXL_API_URL=http://127.0.0.1:8001/generate
SDXL_JOBS_URL=http://127.0.0.1:8001/jobs
SDXL_API_KEY=${SDXL_API_KEY:-dev-local-key}
SDXL_FETCH_TIMEOUT_MS=600000
EOF

echo "==> npm ci && npm run build..."
npm ci
npm run build

STATIC_CSS="$(find .next/static -name '*.css' 2>/dev/null | head -1)"
if [[ -z "$STATIC_CSS" ]]; then
  echo "ERROR: no CSS in .next/static"
  exit 1
fi
echo "==> Build OK ($STATIC_CSS)"

stop_port_3000

echo "==> Starting next start..."
: > /tmp/visual-studio-web.log
nohup npm run start -- -H 0.0.0.0 -p 3000 >> /tmp/visual-studio-web.log 2>&1 &
disown || true

for i in 1 2 3 4 5 6 7 8 9 10; do
  sleep 1
  if grep -q "Ready" /tmp/visual-studio-web.log 2>/dev/null; then
    break
  fi
  if grep -q "EADDRINUSE" /tmp/visual-studio-web.log 2>/dev/null; then
    echo "ERROR: next start failed — port still busy"
    tail -15 /tmp/visual-studio-web.log
    exit 1
  fi
done

if ! ss -tln 2>/dev/null | grep -q ':3000 '; then
  echo "ERROR: nothing listening on 3000"
  tail -20 /tmp/visual-studio-web.log
  exit 1
fi

ASSET_PATH="/_next/static/${STATIC_CSS#*.next/static/}"
ASSET_CODE="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:3000${ASSET_PATH}" || echo 000)"
HTML="$(curl -s http://127.0.0.1:3000/ || true)"

echo "==> Static $ASSET_PATH => HTTP $ASSET_CODE"
if echo "$HTML" | grep -q "Generate frame"; then
  echo "ERROR: still serving OLD UI (Generate frame). Code on disk may be outdated."
  echo "       From Mac run: make spheron-sync"
  exit 1
fi
if echo "$HTML" | grep -qE "Start creating|studio-lime|GenerationDock"; then
  echo "==> NEW UI confirmed (lime / bottom dock)"
else
  echo "WARN: could not confirm new UI markers in HTML — hard-refresh browser (Cmd+Shift+R)"
fi

echo "==> Done. Tunnel: http://127.0.0.1:3000"
