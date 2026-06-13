/** UI-only defaults — not duplicated from API catalog. */

export type StudioMode = "generate" | "product";
export type AspectRatioId =
  | "1:1"
  | "3:4"
  | "4:3"
  | "16:9"
  | "9:16"
  | "ltx"
  | "sd15";

export const SCHEDULER_OPTIONS = [
  { id: "dpm++2m_karras", label: "DPM++ 2M Karras" },
  { id: "euler_trailing", label: "Euler (Lightning)" },
  { id: "euler", label: "Euler" },
] as const;

export const DEFAULT_NEGATIVE =
  "blurry, low quality, deformed, ugly, bad anatomy, bad hands, extra fingers, missing fingers, extra limbs, watermark, text, logo";

export const DEFAULT_SD15_NEGATIVE =
  "lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, fewer digits, cropped, worst quality, low quality, jpeg artifacts, signature, watermark, username, blurry";

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
  { id: "ltx", label: "768 LTX", width: 768, height: 512 },
  { id: "sd15", label: "512 SD1.5", width: 512, height: 512 },
];

export const DEFAULT_PROMPT =
  "luxury product on black velvet, studio softbox lighting, photorealistic commercial shot";

export const DEFAULT_PRODUCT_PROMPT =
  "luxury gold ring on black velvet, studio softbox lighting, photorealistic product photography";

export const fieldClass =
  "h-9 w-full rounded-lg border border-border bg-background/80 px-2.5 text-sm outline-none ring-offset-background focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50";
