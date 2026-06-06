/** Tooltip copy for generation dock controls. */

export const SETTING_HELP = {
  prompt:
    "What you want in the image. Be specific: subject, pose, lighting, camera, style.",
  negativePrompt:
    "What to avoid: bad anatomy, blur, watermarks, extra limbs. Strong negatives improve quality.",
  baseModel:
    "The main weights on GPU. SDXL base for LoRAs; checkpoints (e.g. URPM) are full SD 1.5 models — pick one, not both.",
  lora:
    "Small add-on trained on SDXL base only. Lightning LoRA needs 4 steps + low CFG. Disabled when a checkpoint is selected.",
  profile:
    "Preset bundle for steps, CFG, and scheduler. Pick a preset then fine-tune numbers below — all fields are sent to the GPU.",
  aspect:
    "Output size in pixels. SDXL: 768–1024. SD 1.5 checkpoints: use 512×512.",
  steps:
    "Denoising iterations. Lightning: 4–8. SDXL: 12–35. SD 1.5 URPM: ~20–30.",
  cfg:
    "Prompt strength (guidance scale). Lightning: 0–1. SDXL/URPM: 5–8. Too high = oversaturated.",
  scheduler:
    "Noise schedule. Euler trailing for Lightning; DPM++ 2M Karras for SDXL and SD 1.5.",
  loraWeight:
    "How strongly the LoRA affects the image (0–2). Start at 0.8–1.0 for Lightning.",
  clipSkip:
    "Skip last CLIP layers (SDXL). Usually 2. SD 1.5 checkpoints often use 1.",
  seed:
    "Same seed + same settings = reproducible image. Leave empty for random.",
} as const;

export const ERROR_HELP: Record<string, string> = {
  capacity_reached:
    "The GPU is already rendering one image. Wait until it finishes (or ~30–90s), then click Generate once.",
  rate_limited:
    "Too many clicks in a short time. Wait a few seconds — only one generate runs at a time on the VM.",
  upstream_unreachable:
    "Cannot reach the GPU API. Open the SSH tunnel: ssh -L 8001:127.0.0.1:8001 ubuntu@<VM_IP>",
  checkpoint_not_found:
    "Checkpoint file missing on VM. Upload to models/checkpoints/ and refresh.",
  checkpoint_load_failed:
    "SD 1.5 checkpoint failed to load on GPU (often a library version issue). Restart the API after syncing the latest code.",
  lora_not_found: "LoRA file missing on VM. Upload to models/loras/.",
  lora_not_supported: "LoRAs only work with SDXL base, not SD 1.5 checkpoints.",
};
