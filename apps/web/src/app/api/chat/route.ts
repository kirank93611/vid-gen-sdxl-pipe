import { NextResponse } from "next/server";

import {
  inferenceApiBase,
  inferenceApiKey,
  inferenceFetchTimeoutMs,
} from "@/lib/inference-url";

export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      {
        status: "error",
        message: "Invalid JSON body",
        error_code: "invalid_request",
      },
      { status: 400 },
    );
  }

  try {
    const upstream = await fetch(`${inferenceApiBase()}/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-API-Key": inferenceApiKey(),
      },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(inferenceFetchTimeoutMs()),
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
    const retryAfter = upstream.headers.get("retry-after");
    if (retryAfter) res.headers.set("retry-after", retryAfter);
    return res;
  } catch (err) {
    console.error("[api/chat] upstream fetch failed:", err);
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
