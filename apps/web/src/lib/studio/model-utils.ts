export function isCheckpointModelId(modelId: string): boolean {
  return modelId.startsWith("ckpt_");
}

export function modelKindLabel(
  modelId: string,
): "SDXL base" | "SD 1.5 checkpoint" {
  return isCheckpointModelId(modelId) ? "SD 1.5 checkpoint" : "SDXL base";
}
