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

## Makefile targets (preferred)

```bash
make spheron-sync      # Mac → rsync repo to VM (not on VM)
make spheron-deploy    # Mac: sync + remote deploy-api + deploy-web
make deploy-api        # VM: restart inference API
make deploy-web        # VM: build and restart Next.js
make clean             # Wrapper for clean.sh
make spheron-benchmark # Product similarity benchmark (GPU)
```

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
