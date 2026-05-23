import { NextResponse } from "next/server";

import {
  inferenceApiBase,
  inferenceApiKey,
  inferenceFetchTimeoutMs,
} from "@/lib/inference-url";

export async function GET() {
  try {
    const upstream = await fetch(`${inferenceApiBase()}/models`, {
      headers: { "X-API-Key": inferenceApiKey() },
      signal: AbortSignal.timeout(inferenceFetchTimeoutMs()),
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
    console.error("[api/models] upstream fetch failed:", err);
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
