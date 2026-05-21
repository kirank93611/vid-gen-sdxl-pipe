export type QualityTier = "fast" | "balanced" | "quality";
export type StudioMode = "generate" | "product";
export type AspectRatioId =
  | "1:1"
  | "3:4"
  | "4:3"
  | "16:9"
  | "9:16";

export const QUALITY_TIERS: {
  id: QualityTier;
  label: string;
  steps: string;
}[] = [
  { id: "fast", label: "Fast", steps: "12 steps" },
  { id: "balanced", label: "Balanced", steps: "25 steps" },
  { id: "quality", label: "Quality", steps: "35 steps" },
];

export const ASPECT_RATIOS: {
  id: AspectRatioId;
  label: string;
  width: number;
  height: number;
}[] = [
  { id: "1:1", label: "1:1", width: 1024, height: 1024 },
  { id: "3:4", label: "3:4", width: 768, height: 1024 },
  { id: "4:3", label: "4:3", width: 1024, height: 768 },
  { id: "16:9", label: "16:9", width: 1344, height: 768 },
  { id: "9:16", label: "9:16", width: 768, height: 1344 },
];

export const DEFAULT_PROMPT =
  "luxury product on black velvet, studio softbox lighting, photorealistic commercial shot";

export const DEFAULT_PRODUCT_PROMPT =
  "luxury gold ring on black velvet, studio softbox lighting, photorealistic product photography";
