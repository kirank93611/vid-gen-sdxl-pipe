import { NextResponse } from "next/server";

import {
  inferenceApiBase,
  inferenceFetchTimeoutMs,
} from "@/lib/inference-url";

export async function GET() {
  try {
    const upstream = await fetch(`${inferenceApiBase()}/generation-profiles`, {
      signal: AbortSignal.timeout(Math.min(inferenceFetchTimeoutMs(), 30_000)),
      cache: "no-store",
    });
    const text = await upstream.text();
    return new NextResponse(text, {
      status: upstream.status,
      headers: {
        "Content-Type":
          upstream.headers.get("content-type") ?? "application/json",
      },
    });
  } catch (err) {
    console.error("[api/generation-profiles] upstream fetch failed:", err);
    return NextResponse.json(
      {
        status: "error",
        message: "Could not reach inference API",
        error_code: "upstream_unreachable",
      },
      { status: 502 },
    );
  }
}
