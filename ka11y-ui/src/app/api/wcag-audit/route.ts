import { NextResponse } from "next/server";

const WCAG_API_URL =
  process.env.WCAG_API_URL ??
  "http://localhost:8000/api/v1/combined";

// Submits the job and returns immediately with a jobId. The client polls
// GET /api/wcag-audit/[jobId] for progress — this endpoint must never block,
// since a single long-lived connection through a reverse proxy (e.g. Apache/
// nginx default timeouts of ~60s) gets killed well before a real audit
// (routinely 100s+) finishes.
export async function POST(request: Request) {
  let body: { url?: string; depth?: number; wcagLevel?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      { error: "Invalid request body" },
      { status: 400 },
    );
  }

  const url = body.url?.trim();
  if (!url) {
    return NextResponse.json({ error: "URL is required" }, { status: 400 });
  }

  try {
    new URL(url);
  } catch {
    return NextResponse.json({ error: "Enter a valid URL" }, { status: 400 });
  }

  // Clamp/validate here too — the backend also enforces these bounds, but
  // failing fast avoids a round trip for an obviously bad value.
  const depth = Number.isFinite(body.depth)
    ? Math.min(Math.max(Math.trunc(body.depth as number), 0), 5)
    : 0;
  const wcagLevel = ["A", "AA", "AAA"].includes(body.wcagLevel ?? "")
    ? (body.wcagLevel as string)
    : "AAA";

  try {
    const submitUrl = new URL(`${WCAG_API_URL}/combined-audit`);
    submitUrl.searchParams.set("url", url);
    submitUrl.searchParams.set("max_depth", String(depth));
    submitUrl.searchParams.set("wcag_level", wcagLevel);

    const submitRes = await fetch(submitUrl.toString(), {
      method: "POST",
      signal: AbortSignal.timeout(10000),
    });

    const data = await submitRes.json().catch(() => null);

    if (!submitRes.ok) {
      return NextResponse.json(
        { error: data?.detail || data?.message || "Failed to start combined audit" },
        { status: submitRes.status },
      );
    }

    const jobId = data?.job_id;
    if (!jobId) {
      return NextResponse.json({ error: "No job_id returned" }, { status: 502 });
    }

    return NextResponse.json({ jobId }, { status: 202 });
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
