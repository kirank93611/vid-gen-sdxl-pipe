"use client";

import { useState } from "react";

type OkBody = {
  status: string;
  image_base64: string;
  metadata?: Record<string, unknown>;
};

type ErrBody = {
  status: string;
  message: string;
  request_id: string;
  error_code?: string | null;
  details?: string | null;
};

export function GenerateForm() {
  const [prompt, setPrompt] = useState(
    "A photo of an astronaut riding a horse on Mars, cinematic lighting",
  );
  const [loading, setLoading] = useState(false);
  const [imageSrc, setImageSrc] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [requestId, setRequestId] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setRequestId(null);
    setImageSrc(null);

    try {
      const res = await fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: prompt.trim() }),
      });

      const rid = res.headers.get("x-request-id");
      if (rid) setRequestId(rid);

      const data: unknown = await res.json();

      if (!res.ok) {
        const err = data as ErrBody;
        const msg = err.message ?? res.statusText;
        const extra = err.error_code ? ` (${err.error_code})` : "";
        setError(`${msg}${extra}`);
        return;
      }

      const ok = data as OkBody;
      if (ok.image_base64) {
        setImageSrc(`data:image/jpeg;base64,${ok.image_base64}`);
      } else {
        setError("Unexpected response shape from API");
      }
    } catch {
      setError("Network error — is the Next dev server running?");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex w-full flex-col gap-8">
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <label className="flex flex-col gap-2 text-sm font-medium text-zinc-700 dark:text-zinc-300">
          Prompt
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            rows={4}
            className="rounded-lg border border-zinc-300 bg-white px-3 py-2 text-base font-normal text-zinc-950 shadow-sm outline-none ring-zinc-400 focus:border-zinc-500 focus:ring-2 dark:border-zinc-600 dark:bg-zinc-950 dark:text-zinc-50"
            disabled={loading}
            required
          />
        </label>
        <button
          type="submit"
          disabled={loading || !prompt.trim()}
          className="h-11 rounded-lg bg-zinc-900 px-4 text-sm font-medium text-white transition hover:bg-zinc-800 disabled:pointer-events-none disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-200"
        >
          {loading ? "Generating…" : "Generate"}
        </button>
      </form>

      {requestId && (
        <p className="text-xs text-zinc-500 dark:text-zinc-400">
          Request-ID:{" "}
          <code className="rounded bg-zinc-100 px-1 py-0.5 font-mono text-zinc-800 dark:bg-zinc-800 dark:text-zinc-200">
            {requestId}
          </code>
        </p>
      )}

      {error && (
        <p
          className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200"
          role="alert"
        >
          {error}
        </p>
      )}

      {imageSrc && (
        // eslint-disable-next-line @next/next/no-img-element -- dynamic base64 data URL from API
        <img
          src={imageSrc}
          alt="Generated result"
          className="max-h-[min(70vh,800px)] w-auto max-w-full rounded-lg border border-zinc-200 object-contain dark:border-zinc-700"
        />
      )}
    </div>
  );
}
