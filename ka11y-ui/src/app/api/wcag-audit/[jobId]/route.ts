import { NextResponse } from "next/server";

const WCAG_API_URL =
  process.env.WCAG_API_URL ??
  "http://python:8000/api/v1/combined";

// Single, short-lived status check — the client calls this repeatedly
// instead of one request blocking for the whole audit.
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ jobId: string }> },
) {
  const { jobId } = await params;

  try {
    const pollRes = await fetch(`${WCAG_API_URL}/${jobId}`, {
      signal: AbortSignal.timeout(10000),
    });

    const data = await pollRes.json().catch(() => null);

    if (!pollRes.ok) {
      return NextResponse.json(
        { error: data?.detail || data?.message || "Failed to fetch scan status" },
        { status: pollRes.status },
      );
    }

    return NextResponse.json(data, { status: 200 });
  } catch (err) {
    const timedOut = err instanceof Error && err.name === "TimeoutError";
    return NextResponse.json(
      {
        error: timedOut
          ? "WCAG analysis request timed out"
          : "Unable to reach the WCAG analysis service",
      },
      { status: 502 },
    );
  }
}
