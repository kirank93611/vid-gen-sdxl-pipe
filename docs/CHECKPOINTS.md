# SD 1.5 checkpoints (URPM and others)

> **See also:** [MODELS.md](./MODELS.md) — unified plug-and-play index.

Civitai **checkpoints** are **full models** — not LoRAs. This doc maps the [Civitai “How to use models”](https://github.com/civitai/civitai/wiki/How-to-use-models) A1111 flow to **this repo’s studio**.

---

## Civitai A1111 vs our studio

| Civitai / A1111 | This project |
|-----------------|--------------|
| Put file in `models/Stable-diffusion/` | Put file in **`models/checkpoints/`** on the GPU VM |
| Pick checkpoint in **Stable Diffusion checkpoint** dropdown | Pick **Base model** → `uberRealisticPornMerge_v23Final` |
| LoRA in `models/lora/` + weight ~0.85 | **LoRA dropdown** — SDXL only; **disabled** for checkpoints |
| txt2img steps / CFG / sampler | **Profile** (SD 1.5) or **Tweaks** (Custom) |
| 512×512 typical for SD 1.5 | **Aspect → 512 SD1.5** |

**URPM** = [Uber Realistic Porn Merge v2.3](https://civitai.com/models/2661) — **SD 1.5** merged checkpoint (~2 GB).  
It already includes its training; you do **not** stack SDXL Lightning or other SDXL LoRAs on it.

---

## Your file (already uploaded)

| Item | Value |
|------|--------|
| VM path | `/home/ubuntu/image-sd/models/checkpoints/uberRealisticPornMerge_v23Final.safetensors` |
| API `model_id` | `ckpt_uberRealisticPornMerge_v23Final` |
| Architecture | SD 1.5 (not SDXL) |

---

## Generate URPM in the web UI

**Prereq:** SSH tunnel + `npm run dev` (see [RUNBOOK-SPHERON.md](./RUNBOOK-SPHERON.md)).

1. **Base model** → `uberRealisticPornMerge_v23Final` (under **Checkpoints** in the picker)
2. **LoRA** → **None** (greyed out — checkpoint *is* the model)
3. **Profile** → **SD 1.5** (25 steps, CFG 7, DPM++ Karras)
4. **Aspect** → **512 SD1.5**
5. **Prompt** — photorealistic tags work well, e.g. structure:
   - subject + framing + lighting + `(photorealistic:1.2)` + quality tags
6. **Tweaks** (optional) → negative prompt, seed, or switch **Profile → Custom** for full control

First generation after switching models may take **30–90s** while the 2 GB weights load into VRAM.

---

## Recommended URPM settings

| Setting | Start here | Tweaks (Custom profile) |
|---------|------------|-------------------------|
| Steps | 25 (SD 1.5 profile) | 20–30 |
| CFG | 7 | 5–8 |
| Scheduler | DPM++ 2M Karras | same |
| Size | 512×512 | 512×768 portrait OK |
| LoRA | **None** | N/A |

**Negative prompt (starting point):**

```text
lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, cropped, worst quality, low quality, jpeg artifacts, signature, watermark, blurry
```

URPM has **no single magic trigger word** like some LoRAs; quality comes from prompt + settings above.

---

## API (curl through tunnel)

```powershell
curl -X POST http://127.0.0.1:8001/generate `
  -H "Content-Type: application/json" `
  -H "X-API-Key: dev-local-key" `
  -d "{\"prompt\":\"YOUR PROMPT\",\"model_id\":\"ckpt_uberRealisticPornMerge_v23Final\",\"generation_profile\":\"sd15_standard\",\"width\":512,\"height\":512}"
```

**Custom control** — set `"generation_profile":"custom"` and pass `"steps"`, `"guidance_scale"`, `"scheduler"`, `"negative_prompt"`, `"seed"`.

---

## SDXL + Lightning LoRA (separate workflow)

| | URPM checkpoint | SDXL + Lightning LoRA |
|--|-----------------|------------------------|
| Base model | URPM | SDXL 1.0 Base |
| LoRA | None | `test_lightning_nomark_1024` |
| Profile | SD 1.5 | Lightning 4 |
| Size | 512 | 768×1024 or 1024 |

Pick **one row** per generate — do not mix.

---

## Upload another checkpoint

```powershell
ssh -i C:\Users\Home\.ssh\id_ed25519 ubuntu@<VM_IP> "mkdir -p /home/ubuntu/image-sd/models/checkpoints"

scp -i C:\Users\Home\.ssh\id_ed25519 "C:\Downloads\YourModel.safetensors" `
  ubuntu@<VM_IP>:/home/ubuntu/image-sd/models/checkpoints/
```

Appears in UI as **Base model** with id `ckpt_<filename_without_extension>`.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Model not in dropdown | SSH tunnel; refresh page; `curl http://127.0.0.1:8001/models` |
| `checkpoint_not_found` | File missing under `models/checkpoints/` |
| `lora_not_supported` | You selected a checkpoint + LoRA — clear LoRA |
| Slow / timeout | First load loads 2 GB; raise `SDXL_FETCH_TIMEOUT_MS` in `.env.local` |
| Wrong look at 1024 | Use **512** for SD 1.5 |

See also [LORAS.md](./LORAS.md) for SDXL LoRAs only.
