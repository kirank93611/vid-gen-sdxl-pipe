# Models, LoRAs, and checkpoints (plug-and-play)

Single reference for **adding assets without changing application code** (where possible).

| Asset | Drop-in location | API id | Discovery |
|-------|------------------|--------|-----------|
| **SDXL base** | `models/sdxl-base/` (diffusers) | `sdxl_base` | `model_catalog.py` |
| **SD 1.5 checkpoint** | `models/checkpoints/*.safetensors` | `ckpt_<filename_stem>` | Auto scan |
| **LoRA** | `models/loras/*.safetensors` | `lora_name` = stem | Auto scan |
| **GGUF chat** | `models/<subdir>/` | `tiefighter_20b`, etc. | `model_catalog.py` |
| **Generation preset** | N/A (server config) | `generation_profile` | `generation_profiles.py` |

Env overrides: `SDXL_MODEL_PATH`, `LORAS_DIR`, `CHECKPOINTS_DIR` — see `services/inference-api/api_config.py`.

---

## Quick start (Spheron VM)

```bash
# After upload, list what the API sees:
curl -s http://127.0.0.1:8001/models | jq .
curl -s http://127.0.0.1:8001/loras | jq .
curl -s http://127.0.0.1:8001/generation-profiles | jq .
```

Web studio loads the same catalogs via `/api/models`, `/api/loras`, `/api/generation-profiles`.

---

## SD 1.5 checkpoints

See [CHECKPOINTS.md](./CHECKPOINTS.md) for Civitai → VM upload and UI settings.

- **No LoRAs** on checkpoints (use SDXL base for LoRA stacks).
- First load ~30–90s (VRAM); one model in VRAM at a time.

---

## LoRAs (SDXL only)

See [LORAS.md](./LORAS.md) for Civitai download and upload scripts.

- Lightning LoRA: profile auto-suggests `lightning_4` when name contains `lightning`.
- Character/style LoRAs: include trigger words from Civitai in the prompt.

---

## SDXL base

Default weights: Hugging Face `stabilityai/stable-diffusion-xl-base-1.0` → `models/sdxl-base/`.

To register **additional** SDXL diffusers trees, add an entry to `IMAGE_MODELS` in `services/inference-api/model_catalog.py` (future: optional manifest JSON).

---

## GGUF chat models

Register in `CHAT_MODELS` in `model_catalog.py`, then:

```bash
make download-llm GGUF_MODEL_ID=dolphin_mixtral_8x7b
```

UI: `/chat` + `POST /api/chat`.

---

## Generation profiles

Presets merge onto the request (steps, CFG, scheduler, clip_skip, lora_weight). Use `generation_profile: "custom"` when the client sends all knobs explicitly.

Source of truth: `services/inference-api/generation_profiles.py` → `GET /generation-profiles`.

**Do not duplicate** preset numbers in the frontend — fetch from the API.

---

## Architecture pointers

- Registry / VRAM: `registry.py` (lazy load, evict on switch)
- Policy merge: `generation_profiles.apply_generation_policy`
- HTTP contract: `schemas.py` + integration tests
- Unified listing: `model_registry.list_all_models()`

System design: [ARCHITECTURE.md](../ARCHITECTURE.md). Module map: [CODEBASE.md](./CODEBASE.md).
