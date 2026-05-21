import { NextResponse } from "next/server";

const jobsBase =
  process.env.SDXL_JOBS_URL ?? "http://127.0.0.1:8001/jobs";
const apiKey = process.env.SDXL_API_KEY ?? "dev-local-key";

export async function GET(
  _request: Request,
  context: { params: Promise<{ jobId: string }> },
) {
  const { jobId } = await context.params;
  const url = `${jobsBase.replace(/\/$/, "")}/${jobId}`;

  try {
    const upstream = await fetch(url, {
      headers: { "X-API-Key": apiKey },
      signal: AbortSignal.timeout(30_000),
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
    console.error("[api/jobs] poll failed:", err);
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
