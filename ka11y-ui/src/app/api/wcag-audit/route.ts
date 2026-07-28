import { NextResponse } from "next/server";

const WCAG_API_URL =
  process.env.WCAG_API_URL ??
  "http://python:8000/api/v1/combined";

export async function POST(request: Request) {
  let body: { url?: string };
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

  try {
    // 1. Submit combined audit job
    const submitUrl = new URL(`${WCAG_API_URL}/combined-audit`);
    submitUrl.searchParams.set("url", url);

    const submitRes = await fetch(submitUrl.toString(), {
      method: "POST",
      signal: AbortSignal.timeout(10000),
    });

    if (!submitRes.ok) {
      const data = await submitRes.json().catch(() => null);
      return NextResponse.json(
        { error: data?.detail || data?.message || "Failed to start combined audit" },
        { status: submitRes.status },
      );
    }

    const { job_id } = await submitRes.json();
    if (!job_id) {
      return NextResponse.json({ error: "No job_id returned" }, { status: 500 });
    }

    // 2. Poll for completion
    const startTime = Date.now();
    const TIMEOUT_MS = 300000; // 300s to accommodate longer audits

    while (Date.now() - startTime < TIMEOUT_MS) {
      const pollRes = await fetch(`${WCAG_API_URL}/${job_id}`, {
        signal: AbortSignal.timeout(5000),
      });

      if (!pollRes.ok) {
        // Transient error or 404, we could retry, but let's just wait and try again unless it's fatal
        await new Promise((resolve) => setTimeout(resolve, 3000));
        continue;
      }

      const jobData = await pollRes.json();
      
      if (jobData.status === "completed") {
        return NextResponse.json(jobData.result || {}, { status: 200 });
      }
      
      if (jobData.status === "failed" || jobData.status === "cancelled") {
        return NextResponse.json(
          { error: jobData.error || "Combined audit failed or was cancelled" },
          { status: 502 },
        );
      }

      // Still pending/running
      await new Promise((resolve) => setTimeout(resolve, 3000));
    }

    return NextResponse.json(
      { error: "Audit timed out waiting for completion" },
      { status: 504 },
    );

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
