"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { Check, ChevronDown, Sparkles, Upload } from "lucide-react";

import { SettingLabel } from "@/components/studio/setting-help";
import { GenerationDockMinibar } from "@/components/studio/dock/generation-dock-minibar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { TooltipProvider } from "@/components/ui/tooltip";
import {
  ASPECT_RATIOS,
  DEFAULT_NEGATIVE,
  DEFAULT_PRODUCT_PROMPT,
  DEFAULT_PROMPT,
  DEFAULT_SD15_NEGATIVE,
  SCHEDULER_OPTIONS,
  fieldClass,
  isCheckpointModelId,
  isVideoModelId,
  modelKindLabel,
  findProfile,
  knobsFromProfile,
  profileOptionLabel,
  type AspectRatioId,
  type StudioMode,
} from "@/lib/studio-constants";
import {
  type ApiErr,
  type GenerateOk,
  type GenerationProfileEntry,
  type ImageModelEntry,
  type JobStatus,
  type LoraCatalogEntry,
  fileToBase64,
  fetchGenerationProfiles,
  fetchImageModels,
  fetchLoraCatalog,
  formatApiError,
  formatGenerationMeta,
} from "@/lib/studio-api";
import { SETTING_HELP } from "@/lib/studio-setting-help";
import {
  imageModelLoraBackend,
  isLoraCompatibleWithModel,
  loraBackendLabel,
  type LoraBackend,
} from "@/lib/studio/lora-utils";
import { cn } from "@/lib/utils";

type GenerationDockProps = {
  onImage: (src: string | null) => void;
  onVideo?: (src: string | null) => void;
  onLoading: (loading: boolean) => void;
  onMeta: (line: string | null) => void;
  onError: (message: string | null) => void;
  onMinimizedChange?: (minimized: boolean) => void;
};

export function GenerationDock({
  onImage,
  onVideo,
  onLoading,
  onMeta,
  onError,
  onMinimizedChange,
}: GenerationDockProps) {
  const [mode, setMode] = useState<StudioMode>("generate");
  const [prompt, setPrompt] = useState(DEFAULT_PROMPT);
  const [negativePrompt, setNegativePrompt] = useState(DEFAULT_NEGATIVE);
  const [loadedPreset, setLoadedPreset] = useState("lightning_4");
  const [profiles, setProfiles] = useState<GenerationProfileEntry[]>([]);
  const [modelId, setModelId] = useState("sdxl_base");
  const [imageModels, setImageModels] = useState<ImageModelEntry[]>([]);
  const [steps, setSteps] = useState(4);
  const [guidanceScale, setGuidanceScale] = useState(0);
  const [scheduler, setScheduler] = useState("euler_trailing");
  const [clipSkip, setClipSkip] = useState(2);
  const [seed, setSeed] = useState("");
  const [loraWeight, setLoraWeight] = useState(1);
  const [aspect, setAspect] = useState<AspectRatioId>("3:4");
  const [referenceFile, setReferenceFile] = useState<File | null>(null);
  const [loraName, setLoraName] = useState("");
  const [loras, setLoras] = useState<LoraCatalogEntry[]>([]);
  const [lorasLoading, setLorasLoading] = useState(true);
  const [lorasError, setLorasError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [statusLine, setStatusLine] = useState<string | null>(null);
  const [cooldownSec, setCooldownSec] = useState(0);
  const [minimized, setMinimized] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(true);
  const fileRef = useRef<HTMLInputElement>(null);
  const submittingRef = useRef(false);

  const loadLoras = useCallback(async () => {
    setLorasLoading(true);
    setLorasError(null);
    try {
      const catalog = await fetchLoraCatalog();
      setLoras(catalog.loras);
    } catch (err) {
      setLoras([]);
      setLorasError(
        err instanceof Error
          ? err.message
          : "Could not load LoRAs — is the SSH tunnel open?",
      );
    } finally {
      setLorasLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadLoras();
    void fetchImageModels()
      .then(setImageModels)
      .catch(() => setImageModels([]));
    void fetchGenerationProfiles()
      .then(setProfiles)
      .catch(() => setProfiles([]));
  }, [loadLoras]);

  useEffect(() => {
    onMinimizedChange?.(minimized);
  }, [minimized, onMinimizedChange]);

  useEffect(() => {
    if (cooldownSec <= 0) return;
    const t = window.setTimeout(() => setCooldownSec((s) => Math.max(0, s - 1)), 1000);
    return () => window.clearTimeout(t);
  }, [cooldownSec]);

  const isCheckpoint = isCheckpointModelId(modelId);
  const isVideoModel = isVideoModelId(modelId);
  const modelBackend = imageModelLoraBackend(modelId);
  const activeLora = isCheckpoint ? "" : loraName.trim();
  const selectedLora = loras.find((l) => l.lora_name === activeLora);
  const loraMismatch =
    !!selectedLora &&
    !!modelBackend &&
    !isLoraCompatibleWithModel(
      (selectedLora.backend ?? "sdxl") as LoraBackend,
      modelId,
    );
  const compatibleLoras = loras.filter((l) =>
    modelBackend
      ? isLoraCompatibleWithModel((l.backend ?? "sdxl") as LoraBackend, modelId)
      : false,
  );
  const incompatibleLoras = loras.filter(
    (l) =>
      modelBackend &&
      !isLoraCompatibleWithModel((l.backend ?? "sdxl") as LoraBackend, modelId),
  );
  const aspectDims = ASPECT_RATIOS.find((a) => a.id === aspect)!;
  const videoModels = imageModels.filter(
    (m) =>
      m.model_id.startsWith("ltx_") ||
      m.model_id.startsWith("wan") ||
      m.backend === "ltx2",
  );
  const sdxlModels = imageModels.filter(
    (m) =>
      !isCheckpointModelId(m.model_id) &&
      !m.model_id.startsWith("ltx_") &&
      !m.model_id.startsWith("wan") &&
      m.backend !== "ltx2",
  );
  const checkpointModels = imageModels.filter((m) => isCheckpointModelId(m.model_id));

  const applyPreset = useCallback(
    (id: string) => {
      setLoadedPreset(id);
      const knobs = knobsFromProfile(findProfile(profiles, id));
      if (!knobs) return;
      setSteps(knobs.steps);
      setGuidanceScale(knobs.guidanceScale);
      setScheduler(knobs.scheduler);
      setClipSkip(knobs.clipSkip);
      setLoraWeight(knobs.loraWeight);
    },
    [profiles],
  );

  const markCustom = useCallback(() => {
    setLoadedPreset("custom");
  }, []);

  useEffect(() => {
    if (isCheckpoint) {
      applyPreset("sd15_standard");
      setAspect("sd15");
      setLoraName("");
      setNegativePrompt(DEFAULT_SD15_NEGATIVE);
      return;
    }
    if (isVideoModel) {
      applyPreset("ltx_fast");
      setAspect("ltx");
      return;
    }
    if (activeLora.includes("lightning")) {
      applyPreset("lightning_4");
    }
  }, [activeLora, applyPreset, isCheckpoint, isVideoModel, modelId]);

  useEffect(() => {
    if (!loraMismatch || !activeLora) return;
    setLoraName("");
    onError(
      `${activeLora} requires ${loraBackendLabel(
        (selectedLora?.backend ?? "sdxl") as LoraBackend,
      )} base — not compatible with ${modelKindLabel(modelId)}.`,
    );
  }, [activeLora, loraMismatch, modelId, onError, selectedLora?.backend]);

  function buildRequestBody() {
    const body: Record<string, unknown> = {
      prompt: prompt.trim(),
      negative_prompt: negativePrompt.trim(),
      model_id: modelId,
      generation_profile: "custom",
      width: aspectDims.width,
      height: aspectDims.height,
      steps,
      guidance_scale: guidanceScale,
      scheduler,
      clip_skip: clipSkip,
    };
    const parsedSeed = seed.trim() ? Number.parseInt(seed.trim(), 10) : null;
    if (parsedSeed != null && !Number.isNaN(parsedSeed)) {
      body.seed = parsedSeed;
    }
    if (activeLora) {
      body.lora_name = activeLora;
      body.lora_weight = loraWeight;
    }
    return body;
  }

  function startCooldown(res: Response) {
    const raw = res.headers.get("retry-after");
    const sec = raw ? Number.parseInt(raw, 10) : 5;
    if (!Number.isNaN(sec) && sec > 0) {
      setCooldownSec(sec);
    }
  }

  const runGenerate = useCallback(async () => {
    if (submittingRef.current || cooldownSec > 0) return;
    if (loraMismatch) {
      onError(
        "Selected LoRA does not match the base model. Pick an SDXL LoRA or switch to an LTX/Wan base.",
      );
      return;
    }
    submittingRef.current = true;
    setLoading(true);
    onLoading(true);
    onError(null);
    onMeta(null);
    onImage(null);
    onVideo?.(null);
    setStatusLine(
      isCheckpoint
        ? `GPU · ${modelId}`
        : isVideoModel
          ? activeLora
            ? `GPU · LTX · LoRA ${activeLora} @ ${loraWeight}`
            : `GPU · LTX video`
          : activeLora
            ? `GPU · LoRA ${activeLora} @ ${loraWeight}`
            : "GPU · SDXL base",
    );

    try {
      const res = await fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildRequestBody()),
      });

      const data: unknown = await res.json();
      if (!res.ok) {
        if (res.status === 429) startCooldown(res);
        const retryRaw = res.headers.get("retry-after");
        const retrySec = retryRaw ? Number.parseInt(retryRaw, 10) : undefined;
        onError(
          formatApiError(
            data as ApiErr,
            "Generation failed",
            res.statusText,
            retrySec,
          ),
        );
        return;
      }

      const ok = data as GenerateOk;
      if (ok.video_base64) {
        onVideo?.(`data:video/mp4;base64,${ok.video_base64}`);
      } else {
        onVideo?.(null);
      }
      if (ok.image_base64) {
        onImage(`data:image/jpeg;base64,${ok.image_base64}`);
        const m = ok.metadata;
        if (m) onMeta(formatGenerationMeta(m));
      }
    } catch {
      onError("Network error — check inference API / SSH tunnel.");
    } finally {
      submittingRef.current = false;
      setLoading(false);
      onLoading(false);
      setStatusLine(null);
    }
  }, [
    activeLora,
    aspectDims.height,
    aspectDims.width,
    clipSkip,
    cooldownSec,
    guidanceScale,
    isCheckpoint,
    isVideoModel,
    loraMismatch,
    loraWeight,
    modelId,
    negativePrompt,
    onError,
    onImage,
    onVideo,
    onLoading,
    onMeta,
    prompt,
    scheduler,
    seed,
    steps,
  ]);

  const runProductJob = useCallback(async () => {
    if (!referenceFile) {
      onError("Upload a product reference image for CLIP evaluation.");
      return;
    }
    if (submittingRef.current || cooldownSec > 0) return;
    submittingRef.current = true;

    setLoading(true);
    onLoading(true);
    onError(null);
    onMeta(null);
    onImage(null);
    setStatusLine("Starting correction job…");

    try {
      const refB64 = await fileToBase64(referenceFile);
      const createRes = await fetch("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...buildRequestBody(),
          goal: {
            preserve_product: true,
            product_similarity_min: 0.85,
            task: "product_composite",
            use_inpaint_correction: true,
          },
          max_iterations: 3,
          reference_image_base64: refB64,
        }),
      });

      const createBody: unknown = await createRes.json();
      if (!createRes.ok) {
        if (createRes.status === 429) startCooldown(createRes);
        onError(formatApiError(createBody as ApiErr, "Job create failed"));
        return;
      }

      const jobId = (createBody as { job_id: string }).job_id;
      const deadline = Date.now() + 30 * 60 * 1000;

      while (Date.now() < deadline) {
        await new Promise((r) => setTimeout(r, 700));
        const poll = await fetch(`/api/jobs/${jobId}`);
        const body = (await poll.json()) as JobStatus;
        const iters = body.iterations?.length ?? 0;
        const last = body.iterations?.[iters - 1];
        setStatusLine(
          `${body.status} · ${iters} iter${last?.correction ? ` · ${last.correction}` : ""}`,
        );

        if (["converged", "failed", "error"].includes(body.status)) {
          if (body.image_url) {
            onImage(`/api/jobs/${jobId}/artifact`);
          } else if (body.image_base64) {
            onImage(`data:image/jpeg;base64,${body.image_base64}`);
          }
          if (body.status !== "converged") {
            onError(body.message ?? body.error_code ?? body.status);
          } else if (body.metadata) {
            onMeta(
              formatGenerationMeta(body.metadata, `Job converged · ${iters} iter`),
            );
          } else {
            onMeta(`Job converged · ${iters} iterations`);
          }
          break;
        }
      }
    } catch {
      onError("Network error while running product job.");
    } finally {
      submittingRef.current = false;
      setLoading(false);
      onLoading(false);
      setStatusLine(null);
    }
  }, [
    activeLora,
    aspectDims.height,
    aspectDims.width,
    clipSkip,
    cooldownSec,
    guidanceScale,
    loraWeight,
    modelId,
    negativePrompt,
    onError,
    onImage,
    onLoading,
    onMeta,
    prompt,
    referenceFile,
    scheduler,
    seed,
    steps,
  ]);

  function handleSubmit() {
    if (!prompt.trim() || loading || cooldownSec > 0) return;
    if (mode === "product") void runProductJob();
    else void runGenerate();
  }

  function onModeChange(next: string) {
    const m = next as StudioMode;
    setMode(m);
    setPrompt(m === "product" ? DEFAULT_PRODUCT_PROMPT : DEFAULT_PROMPT);
  }

  const generateDisabled = loading || !prompt.trim() || cooldownSec > 0;
  const generateLabel =
    cooldownSec > 0
      ? `Wait ${cooldownSec}s…`
      : loading
        ? "Rendering…"
        : "Generate";

  return (
    <TooltipProvider delayDuration={200}>
      <motion.div
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1], delay: 0.1 }}
        className="pointer-events-none fixed inset-x-0 bottom-0 z-30 flex justify-center px-2 pb-3 sm:px-4 sm:pb-4"
      >
        <div className="pointer-events-auto w-full max-w-5xl">
          {minimized ? (
            <GenerationDockMinibar
              prompt={prompt}
              statusLine={statusLine}
              loading={loading}
              cooldownSec={cooldownSec}
              generateDisabled={generateDisabled}
              generateLabel={generateLabel}
              onExpand={() => setMinimized(false)}
              onSubmit={handleSubmit}
            />
          ) : (
          <div className="max-h-[38vh] overflow-y-auto rounded-2xl border border-border/90 bg-card/95 shadow-2xl shadow-black/50 backdrop-blur-xl">
            <div className="sticky top-0 z-10 flex items-center justify-between gap-2 border-b border-border/60 bg-card/95 px-3 py-2 backdrop-blur-xl sm:px-4">
              <Tabs value={mode} onValueChange={onModeChange} className="min-w-0 flex-1">
                <TabsList className="h-8 w-full justify-start sm:w-auto">
                  <TabsTrigger value="generate" className="text-xs sm:text-sm">
                    Quick generate
                  </TabsTrigger>
                  <TabsTrigger value="product" className="gap-1.5 text-xs sm:text-sm">
                    Product job
                    <Badge variant="lime" className="ml-0.5 scale-90 normal-case">
                      CLIP
                    </Badge>
                  </TabsTrigger>
                </TabsList>
              </Tabs>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="h-8 w-8 shrink-0"
                onClick={() => setMinimized(true)}
                aria-label="Minimize controls"
              >
                <ChevronDown className="h-4 w-4" />
              </Button>
            </div>

            <div className="space-y-2.5 p-3 sm:p-4">
              <div className="flex gap-2">
                {mode === "product" && (
                  <>
                    <input
                      ref={fileRef}
                      type="file"
                      accept="image/jpeg,image/png,image/webp"
                      className="hidden"
                      onChange={(e) =>
                        setReferenceFile(e.target.files?.[0] ?? null)
                      }
                    />
                    <Button
                      type="button"
                      variant="outline"
                      size="icon"
                      className="h-10 w-10 shrink-0"
                      disabled={loading}
                      onClick={() => fileRef.current?.click()}
                      aria-label="Upload reference"
                    >
                      {referenceFile ? (
                        <Check className="text-[var(--studio-lime)]" />
                      ) : (
                        <Upload className="h-4 w-4" />
                      )}
                    </Button>
                  </>
                )}
                <div className="min-w-0 flex-1">
                  <SettingLabel label="Prompt" help={SETTING_HELP.prompt} />
                  <Textarea
                    id="studio-prompt"
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                    placeholder="Describe the scene you imagine…"
                    rows={2}
                    disabled={loading}
                    className="mt-1 min-h-[44px] border-border/80 bg-background/40 text-sm"
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                        e.preventDefault();
                        handleSubmit();
                      }
                    }}
                  />
                </div>
              </div>

              {isCheckpoint ? (
                <p className="rounded-lg border border-[var(--studio-lime)]/30 bg-[var(--studio-lime)]/5 px-2.5 py-1.5 text-[11px] leading-snug text-muted-foreground">
                  <span className="font-medium text-[var(--studio-lime)]">
                    Checkpoint
                  </span>{" "}
                  — SD 1.5 · 512×512 · no LoRA
                </p>
              ) : activeLora ? (
                <p className="rounded-lg border border-border/80 bg-background/40 px-2.5 py-1.5 text-[11px] text-muted-foreground">
                  <span className="font-medium text-[var(--studio-lime)]">LoRA</span>{" "}
                  — {activeLora}
                </p>
              ) : null}

              <button
                type="button"
                className="flex w-full items-center justify-between rounded-lg border border-border/70 bg-background/30 px-3 py-2 text-left text-xs font-medium text-muted-foreground hover:bg-accent/50"
                onClick={() => setSettingsOpen((v) => !v)}
              >
                <span>Model & generation settings</span>
                <ChevronDown
                  className={cn(
                    "h-4 w-4 shrink-0 transition-transform",
                    settingsOpen && "rotate-180",
                  )}
                />
              </button>

              {settingsOpen && (
              <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-4">
                <div className="flex flex-col gap-1">
                  <SettingLabel label="Base model" help={SETTING_HELP.baseModel} />
                  <select
                    value={modelId}
                    disabled={loading}
                    onChange={(e) => setModelId(e.target.value)}
                    className={fieldClass}
                  >
                    {imageModels.length === 0 ? (
                      <option value={modelId}>{modelId}</option>
                    ) : (
                      <>
                        <optgroup label="SDXL base">
                          {sdxlModels.map((m) => (
                            <option key={m.model_id} value={m.model_id}>
                              {m.display_name}
                            </option>
                          ))}
                        </optgroup>
                        {videoModels.length > 0 && (
                          <optgroup label="Video base">
                            {videoModels.map((m) => (
                              <option
                                key={m.model_id}
                                value={m.model_id}
                                disabled={m.on_disk === false}
                              >
                                {m.display_name}
                                {m.on_disk === false ? " (download weights)" : ""}
                              </option>
                            ))}
                          </optgroup>
                        )}
                        {checkpointModels.length > 0 && (
                          <optgroup label="Checkpoints (SD 1.5)">
                            {checkpointModels.map((m) => (
                              <option key={m.model_id} value={m.model_id}>
                                {m.display_name}
                              </option>
                            ))}
                          </optgroup>
                        )}
                      </>
                    )}
                  </select>
                  <span className="text-[10px] text-muted-foreground">
                    {modelKindLabel(modelId)}
                  </span>
                </div>

                <div className="flex flex-col gap-1">
                  <SettingLabel label="LoRA" help={SETTING_HELP.lora} />
                  <select
                    value={loraName}
                    disabled={loading || isCheckpoint || lorasLoading}
                    onChange={(e) => {
                      const name = e.target.value;
                      setLoraName(name);
                      const entry = loras.find((l) => l.lora_name === name);
                      if (entry?.backend === "ltx") {
                        setModelId("ltx_video");
                      } else if (
                        entry?.backend === "sdxl" &&
                        isVideoModelId(modelId)
                      ) {
                        setModelId("sdxl_base");
                      }
                    }}
                    className={cn(fieldClass, isCheckpoint && "opacity-50")}
                  >
                    <option value="">
                      {isCheckpoint
                        ? "Not available for checkpoints"
                        : modelBackend
                          ? `None (${loraBackendLabel(modelBackend)} base)`
                          : "None"}
                    </option>
                    {compatibleLoras.length > 0 && (
                      <optgroup
                        label={
                          modelBackend
                            ? `${loraBackendLabel(modelBackend)} LoRAs`
                            : "Compatible LoRAs"
                        }
                      >
                        {compatibleLoras.map((l) => (
                          <option key={l.lora_name} value={l.lora_name}>
                            {l.lora_name}
                          </option>
                        ))}
                      </optgroup>
                    )}
                    {incompatibleLoras.length > 0 && (
                      <optgroup label="Requires different base (not available)">
                        {incompatibleLoras.map((l) => (
                          <option
                            key={l.lora_name}
                            value={l.lora_name}
                            disabled
                          >
                            {l.lora_name} — needs{" "}
                            {loraBackendLabel((l.backend ?? "sdxl") as LoraBackend)}
                          </option>
                        ))}
                      </optgroup>
                    )}
                  </select>
                  {!isCheckpoint && incompatibleLoras.length > 0 && (
                    <span className="text-[10px] text-amber-200/90">
                      Some LoRAs need LTX or Wan video base — switch base model to
                      match.
                    </span>
                  )}
                  {lorasError && (
                    <button
                      type="button"
                      className="text-left text-[10px] text-red-300 underline"
                      onClick={() => void loadLoras()}
                    >
                      LoRA list failed — retry
                    </button>
                  )}
                </div>

                <div className="flex flex-col gap-1">
                  <SettingLabel label="Preset" help={SETTING_HELP.profile} />
                  <select
                    value={loadedPreset}
                    disabled={loading}
                    onChange={(e) => applyPreset(e.target.value)}
                    className={fieldClass}
                  >
                    {profiles
                      .filter((p) => {
                        if (isCheckpoint) {
                          return (
                            p.backend === "sd15" || p.profile_id === "custom"
                          );
                        }
                        if (isVideoModel) {
                          return p.backend === "ltx" || p.profile_id === "custom";
                        }
                        return p.backend !== "sd15" && p.backend !== "ltx";
                      })
                      .map((p) => (
                        <option key={p.profile_id} value={p.profile_id}>
                          {profileOptionLabel(p)}
                        </option>
                      ))}
                  </select>
                  <span className="text-[10px] text-muted-foreground">
                    Loads values below; edit any field for full control
                  </span>
                </div>

                <div className="flex flex-col gap-1">
                  <SettingLabel label="Aspect" help={SETTING_HELP.aspect} />
                  <select
                    value={aspect}
                    disabled={loading}
                    onChange={(e) => setAspect(e.target.value as AspectRatioId)}
                    className={fieldClass}
                  >
                    {ASPECT_RATIOS.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.label} ({a.width}×{a.height})
                      </option>
                    ))}
                  </select>
                </div>

                <div className="flex flex-col gap-1">
                  <SettingLabel
                    label="Steps"
                    help={SETTING_HELP.steps}
                    htmlFor="studio-steps"
                  />
                  <input
                    id="studio-steps"
                    type="number"
                    min={1}
                    max={40}
                    value={steps}
                    disabled={loading}
                    onChange={(e) => {
                      markCustom();
                      setSteps(Number(e.target.value));
                    }}
                    className={fieldClass}
                  />
                </div>

                <div className="flex flex-col gap-1">
                  <SettingLabel
                    label="CFG scale"
                    help={SETTING_HELP.cfg}
                    htmlFor="studio-cfg"
                  />
                  <input
                    id="studio-cfg"
                    type="number"
                    min={0}
                    max={12}
                    step={0.1}
                    value={guidanceScale}
                    disabled={loading}
                    onChange={(e) => {
                      markCustom();
                      setGuidanceScale(Number(e.target.value));
                    }}
                    className={fieldClass}
                  />
                </div>

                <div className="flex flex-col gap-1">
                  <SettingLabel label="Scheduler" help={SETTING_HELP.scheduler} />
                  <select
                    value={scheduler}
                    disabled={loading}
                    onChange={(e) => {
                      markCustom();
                      setScheduler(e.target.value);
                    }}
                    className={fieldClass}
                  >
                    {SCHEDULER_OPTIONS.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.label}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="flex flex-col gap-1">
                  <SettingLabel
                    label="LoRA weight"
                    help={SETTING_HELP.loraWeight}
                    htmlFor="studio-lora-weight"
                  />
                  <input
                    id="studio-lora-weight"
                    type="number"
                    min={0}
                    max={2}
                    step={0.05}
                    value={loraWeight}
                    disabled={loading || !activeLora}
                    onChange={(e) => {
                      markCustom();
                      setLoraWeight(Number(e.target.value));
                    }}
                    className={cn(fieldClass, !activeLora && "opacity-50")}
                  />
                </div>

                <div className="flex flex-col gap-1">
                  <SettingLabel
                    label="CLIP skip"
                    help={SETTING_HELP.clipSkip}
                    htmlFor="studio-clip-skip"
                  />
                  <input
                    id="studio-clip-skip"
                    type="number"
                    min={1}
                    max={4}
                    value={clipSkip}
                    disabled={loading}
                    onChange={(e) => {
                      markCustom();
                      setClipSkip(Number(e.target.value));
                    }}
                    className={fieldClass}
                  />
                </div>

                <div className="flex flex-col gap-1">
                  <SettingLabel
                    label="Seed"
                    help={SETTING_HELP.seed}
                    htmlFor="studio-seed"
                  />
                  <input
                    id="studio-seed"
                    type="text"
                    inputMode="numeric"
                    placeholder="Random"
                    value={seed}
                    disabled={loading}
                    onChange={(e) => setSeed(e.target.value)}
                    className={fieldClass}
                  />
                </div>
              </div>
              )}

              <div className="flex flex-col gap-1">
                <SettingLabel
                  label="Negative prompt"
                  help={SETTING_HELP.negativePrompt}
                />
                <Textarea
                  value={negativePrompt}
                  onChange={(e) => setNegativePrompt(e.target.value)}
                  rows={2}
                  disabled={loading}
                  className="min-h-[40px] border-border/80 bg-background/40 text-xs sm:text-sm"
                />
              </div>

              {mode === "product" && referenceFile && (
                <p className="truncate text-xs text-muted-foreground">
                  Reference: {referenceFile.name}
                </p>
              )}
            </div>

            <Separator />

            <div className="sticky bottom-0 flex flex-col gap-2 border-t border-border/60 bg-card/95 px-3 py-2.5 backdrop-blur-xl sm:flex-row sm:items-center sm:px-4">
              {statusLine && (
                <span className="truncate font-mono text-[10px] text-muted-foreground sm:flex-1">
                  {statusLine}
                </span>
              )}
              <Button
                variant="lime"
                size="default"
                disabled={generateDisabled}
                onClick={handleSubmit}
                className="w-full min-w-[120px] sm:ml-auto sm:w-auto"
              >
                {loading ? (
                  generateLabel
                ) : cooldownSec > 0 ? (
                  generateLabel
                ) : (
                  <>
                    <Sparkles className="h-4 w-4" />
                    Generate
                  </>
                )}
              </Button>
            </div>
          </div>
          )}
        </div>
      </motion.div>
    </TooltipProvider>
  );
}
