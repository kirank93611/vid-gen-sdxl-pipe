import type { GenerationProfileEntry } from "@/lib/api/catalog";

export type ProfileKnobs = {
  steps: number;
  guidanceScale: number;
  scheduler: string;
  clipSkip: number;
  loraWeight: number;
};

export function profileOptionLabel(p: GenerationProfileEntry): string {
  const parts: string[] = [];
  if (p.steps != null) parts.push(`${p.steps} steps`);
  if (p.guidance_scale != null) parts.push(`CFG ${p.guidance_scale}`);
  const hint = parts.length ? ` — ${parts.join(" · ")}` : "";
  return `${p.display_name}${hint}`;
}

/** Apply API profile fields to form state; returns null for custom / empty preset. */
export function knobsFromProfile(
  p: GenerationProfileEntry | undefined,
): ProfileKnobs | null {
  if (!p || p.profile_id === "custom") return null;
  if (
    p.steps == null ||
    p.guidance_scale == null ||
    !p.scheduler ||
    p.clip_skip == null
  ) {
    return null;
  }
  return {
    steps: p.steps,
    guidanceScale: p.guidance_scale,
    scheduler: p.scheduler,
    clipSkip: p.clip_skip,
    loraWeight: p.lora_weight ?? 0.8,
  };
}

export function findProfile(
  profiles: GenerationProfileEntry[],
  profileId: string,
): GenerationProfileEntry | undefined {
  return profiles.find((p) => p.profile_id === profileId);
}
