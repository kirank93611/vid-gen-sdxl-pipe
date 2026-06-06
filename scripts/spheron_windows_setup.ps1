# Connect to Spheron VM, sync repo, download SDXL weights (first-time setup).
# Prereq: private key at path in .env.spheron (NOT the public key string).
#
# Usage (from repo root):
#   powershell -ExecutionPolicy Bypass -File scripts/spheron_windows_setup.ps1
#   powershell -ExecutionPolicy Bypass -File scripts/spheron_windows_setup.ps1 -SyncOnly
#   powershell -ExecutionPolicy Bypass -File scripts/spheron_windows_setup.ps1 -SetupOnly
#
# See docs/RUNBOOK-SPHERON.md for full runbook.

param(
    [switch]$SyncOnly,
    [switch]$SetupOnly
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$EnvFile = Join-Path $RepoRoot ".env.spheron"
$Tarball = Join-Path $RepoRoot "spheron_sync.tgz"

if (-not (Test-Path $EnvFile)) {
    Write-Error "Missing $EnvFile — copy .env.spheron.example and set SPHERON_IP + SPHERON_SSH_KEY."
}

Get-Content $EnvFile | ForEach-Object {
    if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)\s*$' -and $_ -notmatch '^\s*#') {
        Set-Variable -Name $Matches[1] -Value $Matches[2].Trim() -Scope Script
    }
}

foreach ($name in @("SPHERON_IP", "SPHERON_USER", "SPHERON_DIR", "SPHERON_SSH_KEY")) {
    if (-not (Get-Variable -Name $name -ErrorAction SilentlyContinue)) {
        Write-Error "Missing $name in .env.spheron"
    }
}

if (-not (Test-Path $SPHERON_SSH_KEY)) {
    Write-Host ""
    Write-Host "BLOCKED: Private key not found at:" -ForegroundColor Red
    Write-Host "  $SPHERON_SSH_KEY"
    Write-Host ""
    Write-Host "Generate: ssh-keygen -t ed25519 -f $SPHERON_SSH_KEY"
    Write-Host "Add the .pub file to Spheron, then re-run this script."
    Write-Host "See docs/RUNBOOK-SPHERON.md"
    exit 1
}

$SshArgs = @(
    "-i", $SPHERON_SSH_KEY,
    "-o", "BatchMode=yes",
    "-o", "StrictHostKeyChecking=accept-new"
)
$HostSpec = "${SPHERON_USER}@${SPHERON_IP}"

Write-Host "Clearing stale known_hosts entry for $SPHERON_IP (if any) ..."
ssh-keygen -R $SPHERON_IP 2>$null | Out-Null

Write-Host "Testing SSH to $HostSpec ..."
& ssh @SshArgs $HostSpec 'echo OK && nvidia-smi --query-gpu=name,memory.total --format=csv,noheader'
if ($LASTEXITCODE -ne 0) {
    Write-Error "SSH failed. Check IP, private key path, and Spheron SSH key on THIS instance."
}

function Sync-RepoToVm {
    Write-Host "Creating remote dir and syncing code (tarball; excludes .venv, models, node_modules) ..."
    & ssh @SshArgs $HostSpec "mkdir -p $SPHERON_DIR"

    if (-not (Get-Command tar -ErrorAction SilentlyContinue)) {
        Write-Error "tar not found — install Git for Windows or use Mac: make spheron-sync"
    }

    Push-Location $RepoRoot
    try {
        tar --exclude=.venv --exclude=models --exclude=node_modules `
            --exclude=apps/web/.next --exclude=generated --exclude=.git `
            --exclude=spheron_sync.tgz -czf $Tarball .
        & scp @SshArgs $Tarball "${HostSpec}:/home/ubuntu/spheron_sync.tgz"
        & ssh @SshArgs $HostSpec "mkdir -p $SPHERON_DIR; tar xzf /home/ubuntu/spheron_sync.tgz -C $SPHERON_DIR; rm -f /home/ubuntu/spheron_sync.tgz"
        if ($LASTEXITCODE -ne 0) { throw "Remote extract failed" }
    } finally {
        Pop-Location
        if (Test-Path $Tarball) { Remove-Item $Tarball -Force }
    }

    # Windows checkouts may use CRLF; bash on Ubuntu needs LF in *.sh
    & ssh @SshArgs $HostSpec "find $SPHERON_DIR/scripts -name '*.sh' -exec sed -i 's/\r$//' {} +"
    Write-Host "Sync done."
}

if (-not $SetupOnly) {
    Sync-RepoToVm
}

if (-not $SyncOnly) {
    Write-Host "Running spheron_setup.sh on VM (~15-25 min: torch + SDXL download) ..."
    & ssh @SshArgs $HostSpec "cd $SPHERON_DIR; bash scripts/spheron_setup.sh"
    if ($LASTEXITCODE -ne 0) { Write-Error "Setup failed on VM" }

    Write-Host "Starting API on VM ..."
    & ssh @SshArgs $HostSpec @"
cd $SPHERON_DIR
export DEVICE=cuda SDXL_MODEL_PATH=$SPHERON_DIR/models/sdxl-base GENERATION_TIMEOUT_SECONDS=300 SDXL_API_KEY=dev-local-key
bash scripts/spheron_restart_api.sh
curl -s http://127.0.0.1:8001/health
"@

    Write-Host ""
    Write-Host "Done. Tunnel from PC:" -ForegroundColor Green
    Write-Host "  ssh -i `"$SPHERON_SSH_KEY`" -L 8001:127.0.0.1:8001 -L 3000:127.0.0.1:3000 $HostSpec"
    Write-Host "Then open http://127.0.0.1:3000 (web on VM) or run npm run dev locally with tunnel on 8001 only."
    Write-Host "Full runbook: docs/RUNBOOK-SPHERON.md"
}
