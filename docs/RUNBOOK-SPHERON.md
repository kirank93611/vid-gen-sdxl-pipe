# Spheron GPU VM — runbook

Step-by-step for connecting a Spheron spot instance, loading SDXL weights, and using the studio from your laptop.

**Targets:** Ubuntu GPU VM (e.g. RTX 6000 Ada), repo at `/home/ubuntu/image-sd` on the VM.

---

## 1. Config files (two places)

| File | Purpose | Changes when |
|------|---------|--------------|
| **`.env.spheron`** (repo root, gitignored) | VM **IP**, SSH user, **private key path** | Every new spot IP |
| **`apps/web/.env.local`** | Web → API URLs | Usually **never** if you use SSH tunnel (`127.0.0.1`) |

Copy template:

```bash
cp .env.spheron.example .env.spheron
```

Example `.env.spheron`:

```env
SPHERON_IP=<VM_PUBLIC_IP>
SPHERON_USER=ubuntu
SPHERON_DIR=/home/ubuntu/image-sd
SPHERON_SSH_KEY=C:\Users\YOU\.ssh\id_ed25519
```

On Mac/Linux use `SPHERON_SSH_KEY=$HOME/.ssh/id_ed25519` and `make spheron-set-ip IP=…`.

---

## 2. SSH keys (one-time per machine)

Spheron needs your **public** key at instance create (or attached to the VM). Your PC needs the matching **private** key file.

### Generate on Windows (PowerShell)

```powershell
ssh-keygen -t ed25519 -f C:\Users\YOU\.ssh\id_ed25519 -C "your-name-spheron"
type C:\Users\YOU\.ssh\id_ed25519.pub
```

Paste the **`.pub` line** into Spheron → SSH keys. Use the VM that was created **with** this key (or add key and restart/redeploy instance).

### Connect

```powershell
ssh -i C:\Users\YOU\.ssh\id_ed25519 ubuntu@<VM_IP>
```

**Do not** paste the public key string into `.env.spheron` — that file points at the **private** file path.

### Host key changed (same IP, new VM)

```powershell
ssh-keygen -R <VM_IP>
```

Then connect again. Common when Spheron recycles an IP.

### Windows App execution aliases

If `python` opens the Microsoft Store: Settings → Apps → App execution aliases → turn **off** `python.exe` / `python3.exe`.

---

## 3. First-time VM setup (empty disk)

### Option A — Windows (PowerShell, from repo root)

```powershell
# 1. Edit .env.spheron with IP + key path
powershell -ExecutionPolicy Bypass -File scripts\spheron_windows_setup.ps1
```

This script: tests SSH → syncs code (tarball) → runs `scripts/spheron_setup.sh` on VM (~15–25 min: PyTorch CUDA + SDXL download).

Then start API on VM:

```powershell
ssh -i C:\Users\YOU\.ssh\id_ed25519 ubuntu@<VM_IP> `
  "cd /home/ubuntu/image-sd; find scripts -name '*.sh' -exec sed -i 's/\r$//' {} +; bash scripts/spheron_restart_api.sh"
```

### Option B — Mac/Linux (Makefile)

```bash
make spheron-set-ip IP=<VM_IP>
make spheron-setup    # rsync + spheron_setup.sh
```

### Verify on VM

```bash
curl -s http://127.0.0.1:8001/health
# expect: "engine":"cuda"
ls models/sdxl-base/unet/diffusion_pytorch_model.fp16.safetensors
```

---

## 4. Use the studio from your laptop

**GPU runs on the VM.** Your browser talks to `localhost`; SSH forwards to the VM.

### Terminal 1 — tunnel (leave open)

```powershell
ssh -i C:\Users\YOU\.ssh\id_ed25519 `
  -L 8001:127.0.0.1:8001 `
  -L 3000:127.0.0.1:3000 `
  ubuntu@<VM_IP>
```

Or API only (local Next.js dev):

```powershell
ssh -i C:\Users\YOU\.ssh\id_ed25519 -L 8001:127.0.0.1:8001 ubuntu@<VM_IP>
```

Mac: `make spheron-tunnel` (reads `.env.spheron`).

### Terminal 2 — web (optional if web runs on VM)

**A.** Tunnel both ports → open http://127.0.0.1:3000 (web on VM via `make deploy-web`).

**B.** Local dev UI + tunneled API only:

```powershell
cd apps\web
copy .env.example .env.local   # keeps 127.0.0.1:8001
npm run dev
```

Open http://localhost:3000

### Health through tunnel

```powershell
curl http://127.0.0.1:8001/health
```

---

## 5. Every new spot instance

| Disk state | Action |
|------------|--------|
| **Same disk**, new IP only | Update `SPHERON_IP` → `make spheron-up` (Mac) or sync + `spheron_bootstrap_quick.sh` (VM) |
| **Fresh disk** | Full setup again (`spheron_setup.sh` or `spheron_windows_setup.ps1`) |

Always run after IP change:

```powershell
ssh-keygen -R <NEW_IP>
```

---

## 6. Code-only update (same VM)

**From Mac:** `make spheron-deploy`

**From Windows:** re-run sync (tarball in `spheron_windows_setup.ps1 -SyncOnly`) then on VM:

```bash
cd ~/image-sd
bash scripts/spheron_restart_api.sh
bash scripts/spheron_deploy_web.sh   # if UI changed
```

---

## 7. Job persistence on VM

Jobs and final JPEGs persist under `generated/` on the VM disk:

- SQLite: `generated/jobs.db`
- Images: `generated/jobs/<job_id>/output.jpg`
- Download: `GET /jobs/{id}/artifact` (via tunnel: same path on `127.0.0.1:8001`)

---

## 8. Logs

On VM:

```bash
tail -f /tmp/sdxl-api.log
tail -f /tmp/visual-studio-web.log
```

---

## 9. Troubleshooting

| Symptom | Fix |
|---------|-----|
| `Permission denied (publickey)` | Private key missing or wrong; public key not on **this** VM — add `.pub` in Spheron or new VM |
| `REMOTE HOST IDENTIFICATION HAS CHANGED` | `ssh-keygen -R <IP>` |
| `Python was not found` (Windows) | Install Python 3.12+, add to PATH; disable Store aliases; use `.venv\Scripts\Activate.ps1` |
| `pipefail: invalid option` on VM | Windows CRLF in `*.sh` — `find scripts -name '*.sh' -exec sed -i 's/\r$//' {} +` |
| `gzip: not in gzip format` (Windows sync) | Use tarball sync in `spheron_windows_setup.ps1` (not raw pipe) |
| API crash on `/jobs/.../artifact` | Ensure `response_model=None` on artifact route (FastAPI file download) |
| Generate slow on PC | API on PC uses CPU — run API on Spheron, tunnel `:8001` |
| `422 use_inpaint_correction` | Restart API on VM after sync |
| Web 500 on `/_next/static` | `rm -rf apps/web/.next && npm run build` on VM |

---

## 10. Command cheat sheet

```powershell
# Windows — full first-time setup
powershell -ExecutionPolicy Bypass -File scripts\spheron_windows_setup.ps1

# Windows — SSH
ssh -i C:\Users\YOU\.ssh\id_ed25519 ubuntu@<IP>

# Windows — tunnel
ssh -i C:\Users\YOU\.ssh\id_ed25519 -L 8001:127.0.0.1:8001 -L 3000:127.0.0.1:3000 ubuntu@<IP>
```

```bash
# Mac — IP + setup
make spheron-set-ip IP=<IP>
make spheron-setup
make spheron-tunnel

# VM — restart API
cd ~/image-sd && bash scripts/spheron_restart_api.sh
```
