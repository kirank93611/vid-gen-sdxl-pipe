# Scripts (operations)

Shell and PowerShell helpers for Spheron GPU VM deploy and benchmarks. Run from **repository root** unless noted.

**Full runbook:** [docs/RUNBOOK-SPHERON.md](../docs/RUNBOOK-SPHERON.md)

---

## Spheron config (repo root)

| File | Purpose |
|------|---------|
| `.env.spheron.example` | Template — copy to `.env.spheron` (gitignored) |
| `.env.spheron` | `SPHERON_IP`, `SPHERON_USER`, `SPHERON_DIR`, `SPHERON_SSH_KEY` (private key **path**) |

Update `SPHERON_IP` after each new spot instance. Mac: `make spheron-set-ip IP=…`

---

## Windows (PowerShell)

| Script | Purpose |
|--------|---------|
| `spheron_windows_setup.ps1` | SSH test → tarball sync → `spheron_setup.sh` → start API |

```powershell
copy .env.spheron.example .env.spheron
# edit IP + SPHERON_SSH_KEY
powershell -ExecutionPolicy Bypass -File scripts\spheron_windows_setup.ps1
powershell -ExecutionPolicy Bypass -File scripts\spheron_windows_setup.ps1 -SyncOnly
powershell -ExecutionPolicy Bypass -File scripts\spheron_windows_setup.ps1 -SetupOnly
```

Sync uses `spheron_sync.tgz` (gitignored), not a raw tar pipe (broken on Windows). Scripts get LF line endings via `sed` on the VM after sync.

**Tunnel:**

```powershell
ssh -i C:\Users\YOU\.ssh\id_ed25519 -L 8001:127.0.0.1:8001 -L 3000:127.0.0.1:3000 ubuntu@<IP>
```

---

## Mac / Linux (Makefile preferred)

```bash
make spheron-set-ip IP=<VM_IP>
make spheron-sync         # rsync code only
make spheron-setup        # first VM: torch + SDXL download
make spheron-up           # recycled VM, models on disk
make spheron-deploy       # sync + restart API + rebuild web
make spheron-tunnel       # SSH -L 3000 and 8001
make deploy-api           # on VM: restart inference API
make deploy-web           # on VM: build and restart Next.js
make spheron-benchmark    # product similarity benchmark (GPU)
```

---

## Shell scripts on VM

| Script | When | Purpose |
|--------|------|---------|
| `spheron_setup.sh` | First boot / wiped disk | venv, PyTorch CUDA, SDXL download |
| `spheron_bootstrap_quick.sh` | New IP, disk kept | Skip model/torch if present; API + web |
| `spheron_restart_api.sh` | After code sync | Kill :8001, uvicorn, wait for `/health` |
| `spheron_deploy_web.sh` | UI changes | Kill :3000, `npm run build`, `next start` |
| `spheron_set_ip.sh` | Mac only | Write `.env.spheron`, clear stale `known_hosts` |
| `spheron_tunnel.sh` | Mac only | Tunnel 3000 / 8001 from `.env.spheron` |
| `spheron_generate.py` | Any | CLI smoke test against `/generate` |
| `clean.sh` | Mac/VM/Win | Remove `.next`, caches, generated artifacts |

---

## Typical flows

### First GPU VM (empty disk)

**Windows:** `spheron_windows_setup.ps1` → tunnel → browser

**Mac:** `make spheron-set-ip` → `make spheron-setup` → `make spheron-tunnel`

### New spot IP (models still on disk)

Update `.env.spheron` → `ssh-keygen -R <IP>` → `make spheron-up` (Mac) or sync + `spheron_bootstrap_quick.sh` (VM)

### Code-only update

**Mac:** `make spheron-deploy`

**Windows:** `spheron_windows_setup.ps1 -SyncOnly` then on VM: `bash scripts/spheron_restart_api.sh`

---

## Environment assumptions

- Repo at `/home/ubuntu/image-sd` on VM (ubuntu user) or `/root/image-sd` (root)
- `.venv` at repo root on VM
- `models/sdxl-base` on VM after `spheron_setup.sh`
- `SDXL_API_KEY` for production (not committed)
- `generated/jobs.db` + `generated/jobs/*/output.jpg` for persisted jobs

See root [README.md](../README.md) for API and UI troubleshooting.
