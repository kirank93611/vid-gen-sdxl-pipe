export type GenerationMetadata = {
  quality_tier?: string | null;
  generation_profile?: string | null;
  model_id?: string | null;
  steps?: number | null;
  guidance_scale?: number | null;
  seed?: number | null;
  scheduler?: string | null;
  lora_name?: string | null;
  lora_weight?: number | null;
  prompt?: string | null;
};

export type GenerateOk = {
  status: string;
  image_base64: string;
  video_base64?: string | null;
  metadata?: GenerationMetadata;
};

export type JobStatus = {
  status: string;
  image_base64?: string | null;
  image_url?: string | null;
  metadata?: GenerationMetadata | null;
  iterations?: {
    attempt: number;
    passed: boolean;
    correction?: string | null;
  }[];
  message?: string | null;
  error_code?: string | null;
};

export function formatGenerationMeta(
  m: GenerationMetadata,
  prefix?: string,
): string {
  const lora =
    m.lora_name != null
      ? `LoRA ${m.lora_name}${m.lora_weight != null ? `@${m.lora_weight}` : ""}`
      : "no LoRA";

  return [
    prefix,
    m.model_id != null && String(m.model_id),
    m.generation_profile != null && `profile ${String(m.generation_profile)}`,
    m.quality_tier != null && `tier ${String(m.quality_tier)}`,
    m.steps != null && `${String(m.steps)} steps`,
    m.guidance_scale != null && `CFG ${String(m.guidance_scale)}`,
    m.scheduler != null && String(m.scheduler),
    m.seed != null && `seed ${String(m.seed)}`,
    lora,
  ]
    .filter(Boolean)
    .join(" · ");
}

export function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      const comma = result.indexOf(",");
      resolve(comma >= 0 ? result.slice(comma + 1) : result);
    };
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}
