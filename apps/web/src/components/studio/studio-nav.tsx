"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Sparkles } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/explore", label: "Explore" },
  { href: "/", label: "Image" },
  { href: "/chat", label: "Chat" },
] as const;

export function StudioNav() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-40 border-b border-border/80 bg-background/80 backdrop-blur-xl">
      <div className="mx-auto flex h-14 max-w-[1600px] items-center justify-between px-4 sm:px-6">
        <div className="flex items-center gap-6">
          <Link href="/" className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--studio-lime)] text-sm font-bold text-black">
              VS
            </div>
            <span className="hidden text-sm font-semibold sm:inline">
              Visual Studio
            </span>
          </Link>
          <nav className="flex items-center gap-1">
            {NAV.map((item) => {
              const active =
                item.href === "/"
                  ? pathname === "/" || pathname === "/studio"
                  : item.href === "/chat"
                    ? pathname === "/chat"
                    : pathname.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "rounded-lg px-3 py-1.5 text-sm transition-colors",
                    active
                      ? "bg-accent text-foreground"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {item.label}
                </Link>
              );
            })}
            <span className="hidden items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm text-muted-foreground/50 lg:flex">
              Product jobs
              <Badge variant="lime" className="normal-case">
                Live
              </Badge>
            </span>
          </nav>
        </div>
        <div className="flex items-center gap-2">
          <Link
            href="/"
            className="hidden items-center gap-1.5 rounded-full border border-border px-3 py-1.5 text-xs text-muted-foreground transition hover:border-[var(--studio-lime)]/30 hover:text-foreground sm:flex"
          >
            <Sparkles className="h-3.5 w-3.5 text-[var(--studio-lime)]" />
            Image editor
          </Link>
        </div>
      </div>
    </header>
  );
}
