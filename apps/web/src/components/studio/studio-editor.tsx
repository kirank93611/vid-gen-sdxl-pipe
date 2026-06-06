"use client";

import { useState } from "react";

import { GenerationDock } from "@/components/studio/generation-dock";
import { StudioCanvas } from "@/components/studio/studio-canvas";
import { cn } from "@/lib/utils";

export function StudioEditor() {
  const [imageSrc, setImageSrc] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [metaLine, setMetaLine] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dockMinimized, setDockMinimized] = useState(false);

  return (
    <div className="flex min-h-[calc(100vh-3.5rem)] flex-col">
      <StudioCanvas
        imageSrc={imageSrc}
        loading={loading}
        metaLine={metaLine}
        dockMinimized={dockMinimized}
      />

      {error && (
        <p
          className={cn(
            "pointer-events-none fixed left-1/2 z-20 max-w-lg -translate-x-1/2 rounded-xl border border-red-900/60 bg-red-950/90 px-4 py-3 text-center text-sm leading-relaxed text-red-200 backdrop-blur-sm",
            dockMinimized ? "bottom-24" : "bottom-[40vh]",
          )}
          role="alert"
        >
          {error}
        </p>
      )}

      <GenerationDock
        onImage={setImageSrc}
        onLoading={setLoading}
        onMeta={setMetaLine}
        onError={setError}
        onMinimizedChange={setDockMinimized}
      />

      <div
        className={cn("shrink-0", dockMinimized ? "h-[4.5rem]" : "h-[38vh]")}
        aria-hidden
      />
    </div>
  );
}
