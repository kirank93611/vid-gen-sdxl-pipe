"use client";

import { ChevronUp, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";

type GenerationDockMinibarProps = {
  prompt: string;
  statusLine: string | null;
  loading: boolean;
  cooldownSec: number;
  generateDisabled: boolean;
  generateLabel: string;
  onExpand: () => void;
  onSubmit: () => void;
};

export function GenerationDockMinibar({
  prompt,
  statusLine,
  loading,
  cooldownSec,
  generateDisabled,
  generateLabel,
  onExpand,
  onSubmit,
}: GenerationDockMinibarProps) {
  return (
    <div className="flex items-center gap-2 rounded-2xl border border-border/90 bg-card/95 px-2 py-2 shadow-2xl shadow-black/50 backdrop-blur-xl sm:gap-3 sm:px-3">
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="h-9 w-9 shrink-0"
        onClick={onExpand}
        aria-label="Expand controls"
      >
        <ChevronUp className="h-4 w-4" />
      </Button>
      <button
        type="button"
        className="min-w-0 flex-1 truncate text-left text-sm text-muted-foreground hover:text-foreground"
        onClick={onExpand}
        title={prompt}
      >
        {prompt.trim() || "Tap to edit prompt & settings…"}
      </button>
      {statusLine && (
        <span className="hidden max-w-[120px] truncate font-mono text-[10px] text-muted-foreground sm:inline">
          {statusLine}
        </span>
      )}
      <Button
        variant="lime"
        size="sm"
        disabled={generateDisabled}
        onClick={onSubmit}
        className="shrink-0 gap-1.5"
      >
        {loading || cooldownSec > 0 ? (
          generateLabel
        ) : (
          <>
            <Sparkles className="h-3.5 w-3.5" />
            Generate
          </>
        )}
      </Button>
    </div>
  );
}
