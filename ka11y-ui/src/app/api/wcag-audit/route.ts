import { NextResponse } from "next/server";

import { forwardedHeaders } from "@/lib/forwardedHeaders";
import { buildCombinedAuditUrl } from "@/lib/combinedAuditUrl";
import { CRAWL_DEPTH_ERROR, parseCrawlDepth } from "@/lib/crawlDepth";

const WCAG_API_URL =
  process.env.WCAG_API_URL ??
  "https://a11y-api.bluecaffeine.in/api/v1/combined";

// Submits the job and returns immediately with a jobId. The client polls
// GET /api/wcag-audit/[jobId] for progress — this endpoint must never block,
// since a single long-lived connection through a reverse proxy (e.g. Apache/
// nginx default timeouts of ~60s) gets killed well before a real audit
// (routinely 100s+) finishes.
export async function POST(request: Request) {
  let body: {
    url?: string;
    maxDepth?: unknown;
    wcagLevel?: string;
    email?: string;
    lang?: string;
  };
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

  // Link depth to crawl beyond `url` itself. Only 0, 1 and 2 are offered and
  // a missing value means 0; anything else is rejected (the Python API
  // enforces the same rule) rather than clamped, so a hand-crafted request
  // cannot widen the crawl.
  const maxDepth = parseCrawlDepth(body.maxDepth);
  if (maxDepth === null) {
    return NextResponse.json({ error: CRAWL_DEPTH_ERROR }, { status: 400 });
  }

  // Conformance level to report against. The backend filter is cumulative —
  // "AA" returns A + AA findings and suppresses AAA. Anything unrecognised
  // falls back to AA rather than silently widening the result set to AAA.
  const wcagLevel = ["A", "AA", "AAA"].includes(body.wcagLevel ?? "")
    ? (body.wcagLevel as string)
    : "AA";

  // Language the findings themselves are rendered in. The backend defaults to
  // "auto", which detects the *audited page's* language — so an English site
  // came back with English reasons even with JA selected in the dashboard.
  // The UI's toggle is an explicit user choice, so pass it through instead.
  // The backend resolves locales by filename (i18n/locales/<lang>.yml), where
  // Japanese is "ja"; sending the UI's "jp" finds no file and silently falls
  // back to English, so map it here. Unknown values fall back to "auto" so the
  // old detect-the-page behaviour still applies when nothing was chosen.
  const UI_LANG_TO_LOCALE: Record<string, string> = { en: "en", jp: "ja" };
  const lang = UI_LANG_TO_LOCALE[body.lang ?? ""] ?? "auto";

  try {
    // Email is only sent when the user supplied one. A deep crawl outlives
    // the browser's wait, so this is how the finished report reaches them.
    const submitUrl = buildCombinedAuditUrl(WCAG_API_URL, {
      url,
      maxDepth,
      wcagLevel,
      lang,
      email: body.email,
    });

    const submitRes = await fetch(submitUrl.toString(), {
      method: "POST",
      // The Python API authorises by session cookie; this handler runs
      // server-side so the browser's cookie has to be forwarded by hand, and
      // so are the x-forwarded-* headers that tell the API this is an https
      // request (without them its https redirect answers 308).
      headers: { ...forwardedHeaders(request.headers), cookie: request.headers.get("cookie") ?? "" },
      signal: AbortSignal.timeout(10000),
    });

    if (submitRes.status === 401) {
      return NextResponse.json({ error: "Not signed in" }, { status: 401 });
    }

    const data = await submitRes.json().catch(() => null);

    if (!submitRes.ok) {
      // A 422's `detail` is FastAPI's list of field errors, not text; passed
      // on as `error` it made New Audit render an object and crash. Send text
      // only: the API's own sentence where it gave one, else a fixed one.
      const text = (v: unknown) => (typeof v === "string" && v ? v : undefined);
      return NextResponse.json(
        {
          error:
            text(data?.detail) ??
            text(data?.error) ??
            text(data?.message) ??
            (submitRes.status === 422
              ? "Check the URL and email address, then try again."
              : "Failed to start combined audit"),
        },
        { status: submitRes.status },
      );
    }

    const jobId = data?.job_id;
    if (!jobId) {
      return NextResponse.json(
        { error: "No job_id returned" },
        { status: 502 },
      );
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
