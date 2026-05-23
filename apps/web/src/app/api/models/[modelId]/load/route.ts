import { NextResponse } from "next/server";

import {
  inferenceApiBase,
  inferenceApiKey,
  inferenceFetchTimeoutMs,
} from "@/lib/inference-url";

type RouteContext = { params: Promise<{ modelId: string }> };

export async function POST(_request: Request, context: RouteContext) {
  const { modelId } = await context.params;
  try {
    const upstream = await fetch(
      `${inferenceApiBase()}/models/${encodeURIComponent(modelId)}/load`,
      {
        method: "POST",
        headers: { "X-API-Key": inferenceApiKey() },
        signal: AbortSignal.timeout(inferenceFetchTimeoutMs()),
      },
    );
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
    console.error("[api/models/load] upstream fetch failed:", err);
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
