"use client";

import { useState } from "react";

import { GenerationDock } from "@/components/studio/generation-dock";
import { StudioCanvas } from "@/components/studio/studio-canvas";

export function StudioEditor() {
  const [imageSrc, setImageSrc] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [metaLine, setMetaLine] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  return (
    <div className="flex min-h-[calc(100vh-3.5rem)] flex-col">
      <StudioCanvas
        imageSrc={imageSrc}
        loading={loading}
        metaLine={metaLine}
      />

      {error && (
        <p
          className="pointer-events-none fixed bottom-[220px] left-1/2 z-20 max-w-md -translate-x-1/2 rounded-xl border border-red-900/60 bg-red-950/90 px-4 py-3 text-center text-sm text-red-200 backdrop-blur-sm"
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
      />

      <div className="h-[200px] shrink-0 sm:h-[220px]" aria-hidden />
    </div>
  );
}
