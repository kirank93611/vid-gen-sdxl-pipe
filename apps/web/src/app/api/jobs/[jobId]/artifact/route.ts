import { NextRequest, NextResponse } from "next/server";

const jobsBase =
  process.env.SDXL_JOBS_URL ?? "http://127.0.0.1:8001/jobs";

export async function GET(
  _request: NextRequest,
  context: { params: Promise<{ jobId: string }> },
) {
  const { jobId } = await context.params;
  const apiKey = process.env.SDXL_API_KEY ?? "dev-local-key";
  const url = `${jobsBase.replace(/\/$/, "")}/${jobId}/artifact`;

  try {
    const upstream = await fetch(url, {
      headers: { "X-API-Key": apiKey },
      cache: "no-store",
    });

    if (!upstream.ok) {
      const text = await upstream.text();
      return new NextResponse(text, { status: upstream.status });
    }

    const bytes = await upstream.arrayBuffer();
    return new NextResponse(bytes, {
      status: 200,
      headers: {
        "Content-Type": upstream.headers.get("Content-Type") ?? "image/jpeg",
        "Cache-Control": "private, max-age=3600",
      },
    });
  } catch (err) {
    console.error("[api/jobs/artifact] upstream fetch failed:", err);
    return NextResponse.json(
      { status: "error", message: "Failed to fetch job artifact" },
      { status: 502 },
    );
  }
}
