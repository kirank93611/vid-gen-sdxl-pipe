/** Re-exports — prefer @/lib/api/* and @/lib/studio/* for new code. */

export type { ApiErr } from "@/lib/api/errors";
export { formatApiError } from "@/lib/api/errors";

export type {
  ImageModelEntry,
  LoraCatalogEntry,
  GenerationProfileEntry,
} from "@/lib/api/catalog";
export {
  fetchImageModels,
  fetchLoraCatalog,
  fetchGenerationProfiles,
} from "@/lib/api/catalog";

export type { GenerationMetadata, GenerateOk, JobStatus } from "@/lib/api/generate";
export { formatGenerationMeta, fileToBase64 } from "@/lib/api/generate";

export type { GeneratePayload } from "@/lib/studio/types";
