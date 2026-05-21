"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowRight, Layers, Sparkles, Wand2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

const container = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.08, delayChildren: 0.05 },
  },
};

const item = {
  hidden: { opacity: 0, y: 16 },
  show: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.45, ease: [0.22, 1, 0.36, 1] as const },
  },
};

export function HomeHero() {
  return (
    <motion.section
      variants={container}
      initial="hidden"
      animate="show"
      className="mx-auto max-w-6xl px-4 py-12 sm:px-6 sm:py-16"
    >
      <motion.div variants={item} className="max-w-2xl">
        <Badge variant="lime" className="mb-4 normal-case">
          Product composite · GPU
        </Badge>
        <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">
          What are we creating{" "}
          <span className="text-[var(--studio-lime)]">today?</span>
        </h1>
        <p className="mt-4 text-lg text-muted-foreground">
          SDXL inference with correction jobs — tier bump, CLIP eval, and
          inpaint when similarity needs a localized fix.
        </p>
        <div className="mt-8 flex flex-wrap gap-3">
          <Button variant="lime" size="lg" asChild>
            <Link href="/">
              Open image editor
              <ArrowRight className="h-4 w-4" />
            </Link>
          </Button>
          <Button variant="outline" size="lg" asChild>
            <Link href="/">Product job</Link>
          </Button>
        </div>
      </motion.div>

      <motion.div
        variants={item}
        className="mt-12 grid gap-4 sm:grid-cols-3"
      >
        {[
          {
            icon: Sparkles,
            title: "Quick generate",
            desc: "Single-shot txt2img with fast / balanced / quality tiers.",
            tag: null,
          },
          {
            icon: Layers,
            title: "Product jobs",
            desc: "Reference + CLIP loop with tier bump and center-mask inpaint.",
            tag: "Live",
          },
          {
            icon: Wand2,
            title: "Draw to edit",
            desc: "Mask + inpaint API ready — canvas UI coming next.",
            tag: "Soon",
          },
        ].map((card) => (
          <motion.div
            key={card.title}
            whileHover={{ y: -4, transition: { duration: 0.2 } }}
            className="rounded-2xl border border-border bg-card/60 p-5 backdrop-blur-sm"
          >
            <div className="mb-3 flex items-center justify-between">
              <card.icon className="h-5 w-5 text-[var(--studio-lime)]" />
              {card.tag && (
                <Badge variant={card.tag === "Live" ? "lime" : "muted"}>
                  {card.tag}
                </Badge>
              )}
            </div>
            <h3 className="font-medium">{card.title}</h3>
            <p className="mt-1 text-sm text-muted-foreground">{card.desc}</p>
          </motion.div>
        ))}
      </motion.div>
    </motion.section>
  );
}
