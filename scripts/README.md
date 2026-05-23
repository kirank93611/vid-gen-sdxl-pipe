# Scripts (operations)

Shell helpers for Spheron GPU VM deploy and benchmarks. Run from **repository root** unless noted.

## Spheron / GPU VM

| Script | Run from | Purpose |
|--------|----------|---------|
| `spheron_setup.sh` | VM (once) | Python venv, deps, model path hints |
| `spheron_vm_bootstrap.sh` | Mac → VM | Initial sync and setup |
| `spheron_deploy_web.sh` | VM | `npm ci`, `next build`, restart web on :3000 |
| `spheron_restart_api.sh` | VM | Restart uvicorn inference API |
| `spheron_generate.py` | Either | CLI smoke test against `/generate` |
| `clean.sh` | Mac or VM | Remove `.next`, caches, generated artifacts |

## Dynamic VM IP (spot instances)

```bash
make spheron-set-ip IP=216.81.248.248   # writes .env.spheron (gitignored)
make spheron-sync                       # uses SPHERON_HOST from .env.spheron
make spheron-tunnel                     # SSH -L 3000 and 8001
```

See `.env.spheron.example` at repo root.

## Makefile targets (preferred)

```bash
make spheron-set-ip IP=…  # save IP after each Spheron deploy
make spheron-sync         # Mac → rsync code only
make spheron-setup        # first VM: full torch + SDXL download
make spheron-up           # recycled VM with models on disk: fast API + web
make spheron-deploy       # sync + restart API + rebuild web
make spheron-tunnel       # browser tunnel to studio
make deploy-api           # VM: restart inference API
make deploy-web           # VM: build and restart Next.js
make clean                # wrapper for clean.sh
make spheron-benchmark    # product similarity benchmark (GPU)
```

| Script | Run on | Purpose |
|--------|--------|---------|
| `spheron_bootstrap_quick.sh` | VM | Fast spin-up if `.venv` + `models/` exist |
| `spheron_set_ip.sh` | Mac | Update `.env.spheron` + clear stale `known_hosts` |
| `spheron_tunnel.sh` | Mac | Tunnel 3000 / 8001 |

## Typical flow

**Mac:** `make spheron-sync` then `make spheron-deploy`  
**VM:** `make deploy-api && make deploy-web` after pulling/syncing code  
**Browser:** SSH tunnel `3000` → VM; API on `8001`

## Environment

Scripts assume:

- Repo at `~/image-sd` on VM (or path you sync to)
- `.venv` at repo root
- `models/sdxl-base` present on disk
- `SDXL_API_KEY` set for production (not committed)

See root [README.md](../README.md) for full troubleshooting (422 schema mismatch, stale Next process, rate limits).
