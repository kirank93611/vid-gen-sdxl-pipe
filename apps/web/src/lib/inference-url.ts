/** Server-side inference API base (no trailing slash). */
export function inferenceApiBase(): string {
  const base = process.env.SDXL_INFERENCE_BASE?.replace(/\/$/, "");
  if (base) return base;
  const generate =
    process.env.SDXL_API_URL ?? "http://127.0.0.1:8001/generate";
  return generate.replace(/\/generate\/?$/, "");
}

export const inferenceApiKey = () =>
  process.env.SDXL_API_KEY ?? "dev-local-key";

export const inferenceFetchTimeoutMs = () =>
  Number(process.env.SDXL_FETCH_TIMEOUT_MS ?? "600000");
