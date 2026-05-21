"use client";

import { motion, AnimatePresence } from "framer-motion";
import { ImageIcon, Loader2 } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";

type StudioCanvasProps = {
  imageSrc: string | null;
  loading?: boolean;
  metaLine?: string | null;
};

export function StudioCanvas({
  imageSrc,
  loading = false,
  metaLine,
}: StudioCanvasProps) {
  return (
    <div className="relative flex min-h-0 flex-1 flex-col items-center justify-center px-4 pb-4 pt-6 sm:px-8">
      <div className="mb-6 text-center">
        <motion.h1
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
          className="text-2xl font-semibold tracking-tight sm:text-3xl"
        >
          Start creating with{" "}
          <span className="text-[var(--studio-lime)]">SDXL</span>
        </motion.h1>
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.08, duration: 0.35 }}
          className="mt-2 max-w-md text-sm text-muted-foreground"
        >
          Describe scene, lighting, and mood — product jobs add reference +
          correction loop on GPU.
        </motion.p>
      </div>

      <div className="relative flex w-full max-w-4xl flex-1 items-center justify-center">
        <AnimatePresence mode="wait">
          {loading && !imageSrc ? (
            <motion.div
              key="loading"
              initial={{ opacity: 0, scale: 0.98 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.98 }}
              className="flex w-full max-w-2xl flex-col items-center gap-4"
            >
              <Skeleton className="aspect-[3/4] w-full max-w-md rounded-2xl" />
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin text-[var(--studio-lime)]" />
                Rendering on GPU…
              </div>
            </motion.div>
          ) : imageSrc ? (
            <motion.div
              key="image"
              initial={{ opacity: 0, scale: 0.96, filter: "blur(8px)" }}
              animate={{ opacity: 1, scale: 1, filter: "blur(0px)" }}
              exit={{ opacity: 0, scale: 0.98 }}
              transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
              className="relative overflow-hidden rounded-2xl border border-border/80 bg-card/40 shadow-2xl shadow-black/40"
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={imageSrc}
                alt="Generated frame"
                className="max-h-[min(58vh,640px)] w-auto object-contain"
                decoding="async"
              />
            </motion.div>
          ) : (
            <motion.div
              key="empty"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex flex-col items-center gap-4 text-center"
            >
              <div className="flex h-20 w-20 items-center justify-center rounded-2xl border border-dashed border-border bg-card/30">
                <ImageIcon className="h-8 w-8 text-muted-foreground/50" />
              </div>
              <p className="max-w-xs text-sm text-muted-foreground">
                Your render appears here. Use the dock below to generate or run
                a product correction job.
              </p>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {metaLine && (
        <motion.p
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          className="mt-4 font-mono text-[11px] text-muted-foreground"
        >
          {metaLine}
        </motion.p>
      )}
    </div>
  );
}
