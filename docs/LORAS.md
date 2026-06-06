# SDXL LoRAs on the GPU VM

> **See also:** [MODELS.md](./MODELS.md) — unified plug-and-play index for LoRAs, checkpoints, and catalog rules.

Optional style adapters loaded from **`models/loras/*.safetensors`**. The API field is **`lora_name`** = filename **without** `.safetensors`.

Example: `models/loras/latex_sdxl_v2.safetensors` → `"lora_name": "latex_sdxl_v2"`

---

## 1. Download on your PC (Civitai)

1. Open the model page on **[Civitai](https://civitai.com)** (prefer the official site over third-party mirrors).
2. Download the **SafeTensor** file (e.g. v2.0 ~163 MB for [Latex SDXL](https://civitai.com/models/125689/latex-sdxl)).
3. Rename for a simple catalog id, e.g. `latex_sdxl_v2.safetensors`.

**Base model note:** Your VM runs **SDXL 1.0 base** (`stabilityai/stable-diffusion-xl-base-1.0`). Many Civitai LoRAs are trained on **Lightning** or **RealVisXL** checkpoints. They often still work but may need different prompts, steps, or `lora_weight` (try `0.6`–`1.0`). For best match, pick LoRAs tagged **SDXL 1.0** base.

---

## 2. Upload to Spheron VM

**Easiest (Windows, from repo root):**

```powershell
powershell -ExecutionPolicy Bypass -File scripts\upload_lora.ps1 -File "$env:USERPROFILE\Downloads\YOUR_FILE.safetensors" -LoraName my_lora_id
```

Or if only one `.safetensors` is in Downloads:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\upload_lora.ps1
```

**Manual scp:**

```powershell
ssh -i C:\Users\YOU\.ssh\id_ed25519 ubuntu@<VM_IP> "mkdir -p /home/ubuntu/image-sd/models/loras"

scp -i C:\Users\YOU\.ssh\id_ed25519 `
  C:\Downloads\latex_sdxl_v2.safetensors `
  ubuntu@<VM_IP>:/home/ubuntu/image-sd/models/loras/latex_sdxl_v2.safetensors
```

Or on the VM after browser download:

```bash
mkdir -p ~/image-sd/models/loras
mv ~/Downloads/*.safetensors ~/image-sd/models/loras/my_lora.safetensors
```

---

## 3. List available LoRAs

Through tunnel:

```powershell
curl http://127.0.0.1:8001/loras
```

---

## 4. Generation profiles (presets)

The API merges **profile blocks** onto your request (`GET /generation-profiles`):

| Profile | Use |
|---------|-----|
| `lightning_4` | SDXL + Lightning LoRA — **4 steps, CFG 0**, euler trailing |
| `lightning_8` | 8 steps, CFG 1 |
| `sdxl_fast` / `balanced` / `quality` | Standard SDXL base (12–35 steps) |
| `sd15_standard` | SD 1.5 **checkpoints** in `models/checkpoints/` |
| `custom` | You set steps, CFG, scheduler in the UI **Tweaks** panel |

Selecting a Lightning LoRA **auto-applies** `lightning_4` (overrides legacy Fast tier).

## 5. SD 1.5 checkpoints (not LoRAs)

Single-file `.safetensors` checkpoints live in **`models/checkpoints/`** (e.g. URPM).

- API model id: `ckpt_<filename_stem>` → `ckpt_uberRealisticPornMerge_v23Final`
- Listed in `GET /models` when the file exists on disk
- **LoRAs do not apply** to checkpoints (SDXL LoRAs ≠ merged checkpoints)

Upload:

```powershell
scp -i C:\Users\Home\.ssh\id_ed25519 "C:\Users\Home\Downloads\uberRealisticPornMerge_v23Final.safetensors" ubuntu@<VM_IP>:/home/ubuntu/image-sd/models/checkpoints/
```

## 6. Generate with LoRA

**curl:**

```powershell
curl -X POST http://127.0.0.1:8001/generate `
  -H "Content-Type: application/json" `
  -H "X-API-Key: dev-local-key" `
  -d "{\"prompt\": \"your prompt here\", \"quality_tier\": \"balanced\", \"lora_name\": \"latex_sdxl_v2\", \"lora_weight\": 0.8}"
```

**Web UI:** optional **LoRA name** field on the Generate tab (same id as filename stem).

**Jobs:** add `"lora_name"` / `"lora_weight"` to the job JSON (generate steps only; inpaint steps do not reload LoRA yet).

---

## 5. Env (optional)

| Variable | Default |
|----------|---------|
| `LORAS_DIR` | `<repo>/models/loras` |

---

## 6. After code sync

Restart API on VM:

```bash
cd ~/image-sd && bash scripts/spheron_restart_api.sh
```

Windows: re-run `spheron_windows_setup.ps1 -SyncOnly` then restart API on VM.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `lora_not_found` | File missing or wrong name — must match `lora_name.safetensors` exactly |
| `invalid_lora_name` | Use only letters, numbers, `.`, `_`, `-` (no paths) |
| Weak / wrong look | LoRA trained for another checkpoint; adjust weight or prompt |
| `internal_error` + PEFT | VM missing `peft` — on VM: `source .venv/bin/activate && pip install peft`, then restart API |
| OOM | LoRA adds little VRAM; lower resolution if needed |

See also [RUNBOOK-SPHERON.md](./RUNBOOK-SPHERON.md).
