import { NextResponse } from "next/server";

const inferenceUrl =
  process.env.SDXL_API_URL ?? "http://127.0.0.1:8001/generate";
const apiKey = process.env.SDXL_API_KEY ?? "dev-local-key";
const fetchTimeoutMs = Number(process.env.SDXL_FETCH_TIMEOUT_MS ?? "600000");

export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      {
        status: "error",
        message: "Invalid JSON body",
        request_id: "",
        error_code: "invalid_request",
      },
      { status: 400 },
    );
  }

  try {
    const upstream = await fetch(inferenceUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-API-Key": apiKey,
      },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(fetchTimeoutMs),
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
    console.error("[api/generate] upstream fetch failed:", err);
    return NextResponse.json(
      {
        status: "error",
        message: "Could not reach inference API",
        request_id: "",
        error_code: "upstream_unreachable",
      },
      { status: 502 },
    );
  }
}
