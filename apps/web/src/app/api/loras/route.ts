import { NextResponse } from "next/server";

import {
  inferenceApiBase,
  inferenceFetchTimeoutMs,
} from "@/lib/inference-url";

/** Proxy GET /loras — public catalog on inference API (no auth). */
export async function GET() {
  try {
    const upstream = await fetch(`${inferenceApiBase()}/loras`, {
      signal: AbortSignal.timeout(Math.min(inferenceFetchTimeoutMs(), 30_000)),
      cache: "no-store",
    });
    const text = await upstream.text();
    const res = new NextResponse(text, {
      status: upstream.status,
      headers: {
        "Content-Type":
          upstream.headers.get("content-type") ?? "application/json",
      },
    });
    const rid = upstream.headers.get("x-request-id");
    if (rid) res.headers.set("x-request-id", rid);
    return res;
  } catch (err) {
    console.error("[api/loras] upstream fetch failed:", err);
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
