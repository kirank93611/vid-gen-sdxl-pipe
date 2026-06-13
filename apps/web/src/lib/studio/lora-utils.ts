export type LoraBackend = "sdxl" | "ltx" | "wan";

export function imageModelLoraBackend(
  modelId: string,
): LoraBackend | null {
  if (modelId.startsWith("ckpt_")) return null;
  const lower = modelId.toLowerCase();
  if (lower.startsWith("wan")) return "wan";
  if (lower.startsWith("ltx")) return "ltx";
  return "sdxl";
}

export function loraBackendLabel(backend: LoraBackend): string {
  switch (backend) {
    case "ltx":
      return "LTX video";
    case "wan":
      return "Wan video";
    default:
      return "SDXL";
  }
}

export function isLoraCompatibleWithModel(
  loraBackend: LoraBackend,
  modelId: string,
): boolean {
  const modelBackend = imageModelLoraBackend(modelId);
  return modelBackend !== null && loraBackend === modelBackend;
}
