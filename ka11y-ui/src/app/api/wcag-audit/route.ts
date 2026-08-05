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
  let body: { url?: string; maxDepth?: number; wcagLevel?: string; email?: string };
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

  // Extra pages to crawl from the site's sitemap/links beyond `url` itself.
  // Clamped to match the Python/Node-side cap (0-5) so an out-of-range value
  // here fails fast instead of being silently reinterpreted downstream.
  const rawDepth = body.maxDepth;
  const maxDepth =
    typeof rawDepth === "number" && Number.isFinite(rawDepth)
      ? Math.min(Math.max(Math.trunc(rawDepth), 0), 5)
      : 0;

  // Conformance level to report against. The backend filter is cumulative —
  // "AA" returns A + AA findings and suppresses AAA. Anything unrecognised
  // falls back to AA rather than silently widening the result set to AAA.
  const wcagLevel = ["A", "AA", "AAA"].includes(body.wcagLevel ?? "")
    ? (body.wcagLevel as string)
    : "AA";

  try {
    const submitUrl = new URL(`${WCAG_API_URL}/combined-audit`);
    submitUrl.searchParams.set("url", url);
    submitUrl.searchParams.set("max_depth", String(maxDepth));
    submitUrl.searchParams.set("wcag_level", wcagLevel);
    // Only sent when the user supplied one. A deep crawl outlives the browser's
    // wait, so this is how the finished report reaches them.
    const email = body.email?.trim();
    if (email) submitUrl.searchParams.set("email", email);

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
