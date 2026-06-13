import type { ApiErr } from "@/lib/api/errors";

export type ImageModelEntry = {
  model_id: string;
  display_name: string;
  family: string;
  backend?: string;
  on_disk?: boolean;
};

export type LoraCatalogEntry = {
  lora_name: string;
  filename: string;
  backend?: "sdxl" | "ltx" | "wan";
};

export type GenerationProfileEntry = {
  profile_id: string;
  display_name: string;
  description: string;
  steps: number | null;
  guidance_scale: number | null;
  scheduler: string | null;
  clip_skip: number | null;
  lora_weight: number | null;
  backend: string;
};

export async function fetchImageModels(): Promise<ImageModelEntry[]> {
  const res = await fetch("/api/models", { cache: "no-store" });
  const data: unknown = await res.json();
  if (!res.ok) throw new Error("Could not load models");
  const models = (data as { models: ImageModelEntry[] }).models ?? [];
  return models.filter((m) => m.family === "image");
}

export async function fetchLoraCatalog(): Promise<{
  loras: LoraCatalogEntry[];
  lora_dir?: string;
}> {
  const res = await fetch("/api/loras", { cache: "no-store" });
  const data: unknown = await res.json();
  if (!res.ok) {
    const err = data as ApiErr;
    throw new Error(
      err.message ?? "Could not load LoRA catalog from GPU VM",
    );
  }
  const body = data as { loras: LoraCatalogEntry[]; lora_dir?: string };
  return { loras: body.loras ?? [], lora_dir: body.lora_dir };
}

export async function fetchGenerationProfiles(): Promise<
  GenerationProfileEntry[]
> {
  const res = await fetch("/api/generation-profiles", { cache: "no-store" });
  const data: unknown = await res.json();
  if (!res.ok) throw new Error("Could not load generation profiles");
  return (data as { profiles: GenerationProfileEntry[] }).profiles ?? [];
}
