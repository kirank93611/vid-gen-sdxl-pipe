/** Generate request shape mirrored from FastAPI GenerateRequest (subset). */
export type GeneratePayload = {
  prompt: string;
  negative_prompt?: string;
  model_id?: string;
  generation_profile?: string;
  width: number;
  height: number;
  steps?: number;
  guidance_scale?: number;
  scheduler?: string;
  clip_skip?: number;
  seed?: number | null;
  lora_name?: string;
  lora_weight?: number;
};
