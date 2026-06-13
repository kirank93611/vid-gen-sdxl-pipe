export function isCheckpointModelId(modelId: string): boolean {
  return modelId.startsWith("ckpt_");
}

export function isVideoModelId(modelId: string): boolean {
  return modelId.startsWith("ltx_") || modelId.startsWith("wan");
}

export function modelKindLabel(
  modelId: string,
): "SDXL base" | "SD 1.5 checkpoint" | "LTX video" | "Wan video" {
  if (isCheckpointModelId(modelId)) return "SD 1.5 checkpoint";
  if (modelId.startsWith("ltx_")) return "LTX video";
  if (modelId.startsWith("wan")) return "Wan video";
  return "SDXL base";
}
