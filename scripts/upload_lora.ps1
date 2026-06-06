# Upload a LoRA .safetensors from your PC to the Spheron VM.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\upload_lora.ps1 -File "C:\Users\Home\Downloads\my_lora.safetensors"
#   powershell -ExecutionPolicy Bypass -File scripts\upload_lora.ps1 -File "C:\Users\Home\Downloads\my_lora.safetensors" -LoraName latex_sdxl_v2
#   powershell -ExecutionPolicy Bypass -File scripts\upload_lora.ps1   # newest .safetensors in Downloads

param(
    [string]$File = "",
    [string]$LoraName = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$EnvFile = Join-Path $RepoRoot ".env.spheron"

if (-not (Test-Path $EnvFile)) {
    Write-Error "Missing .env.spheron — set SPHERON_IP and SPHERON_SSH_KEY first."
}

Get-Content $EnvFile | ForEach-Object {
    if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)\s*$' -and $_ -notmatch '^\s*#') {
        Set-Variable -Name $Matches[1] -Value $Matches[2].Trim() -Scope Script
    }
}

if (-not $File) {
    $downloads = Join-Path $env:USERPROFILE "Downloads"
    $candidates = Get-ChildItem $downloads -Filter "*.safetensors" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending
    if ($candidates.Count -eq 0) {
        Write-Error "No .safetensors in $downloads — pass -File path to your Civitai download."
    }
    if ($candidates.Count -gt 1) {
        Write-Host "Multiple LoRAs in Downloads — using newest:"
        $candidates | Select-Object -First 5 Name, LastWriteTime | Format-Table
    }
    $File = $candidates[0].FullName
}

if (-not (Test-Path $File)) {
    Write-Error "File not found: $File"
}

if (-not $LoraName) {
    $LoraName = [System.IO.Path]::GetFileNameWithoutExtension($File)
    # Civitai names are messy — suggest a clean id
    $LoraName = ($LoraName -replace '[^\w\.\-]', '_').Trim('_')
    Write-Host "Using lora_name: $LoraName (override with -LoraName)"
}

$remoteDir = "$SPHERON_DIR/models/loras"
$remoteFile = "$remoteDir/${LoraName}.safetensors"

Write-Host "Uploading:"
Write-Host "  From: $File"
Write-Host "  To:   ${SPHERON_USER}@${SPHERON_IP}:$remoteFile"

ssh-keygen -R $SPHERON_IP 2>$null | Out-Null
& ssh -i $SPHERON_SSH_KEY -o StrictHostKeyChecking=accept-new "${SPHERON_USER}@${SPHERON_IP}" "mkdir -p $remoteDir"
& scp -i $SPHERON_SSH_KEY -o StrictHostKeyChecking=accept-new $File "${SPHERON_USER}@${SPHERON_IP}:${remoteFile}"

Write-Host ""
Write-Host "Done. Verify:" -ForegroundColor Green
Write-Host "  curl http://127.0.0.1:8001/loras   (with SSH tunnel open)"
Write-Host "  Use lora_name: $LoraName in Generate UI or API"
