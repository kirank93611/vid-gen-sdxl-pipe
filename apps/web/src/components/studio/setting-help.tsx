"use client";

import { Info } from "lucide-react";

import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

type SettingHelpProps = {
  label: string;
  help: string;
  htmlFor?: string;
  className?: string;
};

export function SettingLabel({ label, help, htmlFor, className }: SettingHelpProps) {
  return (
    <span className={cn("inline-flex items-center gap-1.5", className)}>
      {htmlFor ? (
        <label htmlFor={htmlFor} className="text-[10px] uppercase tracking-wide text-muted-foreground">
          {label}
        </label>
      ) : (
        <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
          {label}
        </span>
      )}
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            className="inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            aria-label={`About ${label}`}
          >
            <Info className="h-3 w-3" />
          </button>
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-[240px] text-left leading-relaxed">
          {help}
        </TooltipContent>
      </Tooltip>
    </span>
  );
}
