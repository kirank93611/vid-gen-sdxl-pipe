/** @deprecated Import from @/lib/studio/defaults and @/lib/studio/model-utils */
export type { StudioMode, AspectRatioId } from "@/lib/studio/defaults";
export {
  SCHEDULER_OPTIONS,
  DEFAULT_NEGATIVE,
  DEFAULT_SD15_NEGATIVE,
  ASPECT_RATIOS,
  DEFAULT_PROMPT,
  DEFAULT_PRODUCT_PROMPT,
  fieldClass,
} from "@/lib/studio/defaults";
export { isCheckpointModelId, modelKindLabel } from "@/lib/studio/model-utils";
export { knobsFromProfile, findProfile, profileOptionLabel } from "@/lib/studio/profile-utils";
export type { ProfileKnobs } from "@/lib/studio/profile-utils";

/** Profile id is any string returned by GET /generation-profiles */
export type GenerationProfileId = string;
