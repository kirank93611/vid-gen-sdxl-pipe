"use client";

import { useCallback, useRef, useState } from "react";
import { motion } from "framer-motion";
import {
  Check,
  ImagePlus,
  Ratio,
  Sparkles,
  Upload,
  Zap,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import {
  ASPECT_RATIOS,
  DEFAULT_PRODUCT_PROMPT,
  DEFAULT_PROMPT,
  QUALITY_TIERS,
  type AspectRatioId,
  type QualityTier,
  type StudioMode,
} from "@/lib/studio-constants";
import {
  type ApiErr,
  type GenerateOk,
  type JobStatus,
  fileToBase64,
  formatApiError,
} from "@/lib/studio-api";
import { cn } from "@/lib/utils";

type GenerationDockProps = {
  onImage: (src: string | null) => void;
  onLoading: (loading: boolean) => void;
  onMeta: (line: string | null) => void;
  onError: (message: string | null) => void;
};

export function GenerationDock({
  onImage,
  onLoading,
  onMeta,
  onError,
}: GenerationDockProps) {
  const [mode, setMode] = useState<StudioMode>("generate");
  const [prompt, setPrompt] = useState(DEFAULT_PROMPT);
  const [qualityTier, setQualityTier] = useState<QualityTier>("fast");
  const [aspect, setAspect] = useState<AspectRatioId>("3:4");
  const [referenceFile, setReferenceFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [statusLine, setStatusLine] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const aspectDims = ASPECT_RATIOS.find((a) => a.id === aspect)!;

  const runGenerate = useCallback(async () => {
    setLoading(true);
    onLoading(true);
    onError(null);
    onMeta(null);
    onImage(null);
    setStatusLine(null);

    try {
      const res = await fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt: prompt.trim(),
          quality_tier: qualityTier,
          width: aspectDims.width,
          height: aspectDims.height,
        }),
      });

      const data: unknown = await res.json();
      if (!res.ok) {
        onError(formatApiError(data as ApiErr, "Generation failed", res.statusText));
        return;
      }

      const ok = data as GenerateOk;
      if (ok.image_base64) {
        onImage(`data:image/jpeg;base64,${ok.image_base64}`);
        const m = ok.metadata;
        if (m) {
          onMeta(
            [
              m.quality_tier != null && `tier ${String(m.quality_tier)}`,
              m.steps != null && `${String(m.steps)} steps`,
              m.seed != null && `seed ${String(m.seed)}`,
            ]
              .filter(Boolean)
              .join(" · "),
          );
        }
      }
    } catch {
      onError("Network error — check inference API / proxy.");
    } finally {
      setLoading(false);
      onLoading(false);
    }
  }, [
    aspectDims.height,
    aspectDims.width,
    onError,
    onImage,
    onLoading,
    onMeta,
    prompt,
    qualityTier,
  ]);

  const runProductJob = useCallback(async () => {
    if (!referenceFile) {
      onError("Upload a product reference image for CLIP evaluation.");
      return;
    }

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
          goal: {
            preserve_product: true,
            product_similarity_min: 0.85,
            task: "product_composite",
            use_inpaint_correction: true,
          },
          prompt: prompt.trim(),
          quality_tier: qualityTier,
          max_iterations: 3,
          width: aspectDims.width,
          height: aspectDims.height,
          reference_image_base64: refB64,
        }),
      });

      const createBody: unknown = await createRes.json();
      if (!createRes.ok) {
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
          if (body.image_base64) {
            onImage(`data:image/jpeg;base64,${body.image_base64}`);
          }
          if (body.status !== "converged") {
            onError(body.message ?? body.error_code ?? body.status);
          } else {
            onMeta(`Job converged · ${iters} iterations`);
          }
          break;
        }
      }
    } catch {
      onError("Network error while running product job.");
    } finally {
      setLoading(false);
      onLoading(false);
      setStatusLine(null);
    }
  }, [
    aspectDims.height,
    aspectDims.width,
    onError,
    onImage,
    onLoading,
    onMeta,
    prompt,
    qualityTier,
    referenceFile,
  ]);

  function handleSubmit() {
    if (!prompt.trim() || loading) return;
    if (mode === "product") void runProductJob();
    else void runGenerate();
  }

  function onModeChange(next: string) {
    const m = next as StudioMode;
    setMode(m);
    setPrompt(m === "product" ? DEFAULT_PRODUCT_PROMPT : DEFAULT_PROMPT);
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 24 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1], delay: 0.1 }}
      className="pointer-events-none fixed inset-x-0 bottom-0 z-30 flex justify-center px-3 pb-4 sm:px-6"
    >
      <div className="pointer-events-auto w-full max-w-4xl">
        <div className="mb-2 flex justify-center">
          <Badge variant="trending" className="normal-case">
            SDXL · tier bump · inpaint correction
          </Badge>
        </div>

        <div className="rounded-2xl border border-border/90 bg-card/95 p-3 shadow-2xl shadow-black/50 backdrop-blur-xl sm:p-4">
          <Tabs value={mode} onValueChange={onModeChange} className="mb-3">
            <TabsList className="w-full justify-start sm:w-auto">
              <TabsTrigger value="generate">Quick generate</TabsTrigger>
              <TabsTrigger value="product" className="gap-1.5">
                Product job
                <Badge variant="lime" className="ml-0.5 scale-90 normal-case">
                  CLIP
                </Badge>
              </TabsTrigger>
            </TabsList>
          </Tabs>

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
                  className="shrink-0"
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
            <Textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Describe the scene you imagine…"
              rows={2}
              disabled={loading}
              className="min-h-[52px] flex-1 border-0 bg-transparent focus-visible:ring-0"
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                  e.preventDefault();
                  handleSubmit();
                }
              }}
            />
          </div>

          <Separator className="my-3" />

          <div className="flex flex-wrap items-center gap-2">
            <Button variant="chip" size="sm" disabled className="gap-1.5">
              <ImagePlus className="h-3.5 w-3.5" />
              SDXL base
            </Button>

            <Popover>
              <PopoverTrigger asChild>
                <Button variant="chip" size="sm" disabled={loading}>
                  <Ratio className="h-3.5 w-3.5" />
                  {aspect}
                </Button>
              </PopoverTrigger>
              <PopoverContent align="start" className="w-40 p-1">
                {ASPECT_RATIOS.map((a) => (
                  <button
                    key={a.id}
                    type="button"
                    className={cn(
                      "flex w-full items-center justify-between rounded-lg px-3 py-2 text-sm transition-colors hover:bg-accent",
                      aspect === a.id && "text-[var(--studio-lime)]",
                    )}
                    onClick={() => setAspect(a.id)}
                  >
                    {a.label}
                    {aspect === a.id && <Check className="h-3.5 w-3.5" />}
                  </button>
                ))}
              </PopoverContent>
            </Popover>

            <Popover>
              <PopoverTrigger asChild>
                <Button variant="chip" size="sm" disabled={loading}>
                  <Zap className="h-3.5 w-3.5" />
                  {QUALITY_TIERS.find((t) => t.id === qualityTier)?.label}
                </Button>
              </PopoverTrigger>
              <PopoverContent align="start" className="w-44 p-1">
                {QUALITY_TIERS.map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    className={cn(
                      "flex w-full flex-col items-start rounded-lg px-3 py-2 text-left text-sm hover:bg-accent",
                      qualityTier === t.id && "text-[var(--studio-lime)]",
                    )}
                    onClick={() => setQualityTier(t.id)}
                  >
                    <span>{t.label}</span>
                    <span className="text-[10px] text-muted-foreground">
                      {t.steps}
                    </span>
                  </button>
                ))}
              </PopoverContent>
            </Popover>

            {mode === "product" && referenceFile && (
              <span className="truncate text-[11px] text-muted-foreground max-w-[120px]">
                {referenceFile.name}
              </span>
            )}

            <div className="ml-auto flex items-center gap-2">
              {statusLine && (
                <span className="hidden font-mono text-[10px] text-muted-foreground sm:inline">
                  {statusLine}
                </span>
              )}
              <Button
                variant="lime"
                size="lg"
                disabled={loading || !prompt.trim()}
                onClick={handleSubmit}
                className="min-w-[140px]"
              >
                {loading ? (
                  "Rendering…"
                ) : (
                  <>
                    <Sparkles className="h-4 w-4" />
                    Generate
                  </>
                )}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </motion.div>
  );
}
