import { NextResponse } from "next/server";

const WCAG_API_URL =
  process.env.WCAG_API_URL ??
  "http://ec2-34-228-40-177.compute-1.amazonaws.com:3000/api/v1/analyse-url-wcag";

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
    const upstream = await fetch(WCAG_API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
      signal: AbortSignal.timeout(150000),
    });

    const data = await upstream.json().catch(() => null);

    if (!upstream.ok) {
      return NextResponse.json(
        { error: data?.message ?? "WCAG analysis failed" },
        { status: upstream.status },
      );
    }

    return NextResponse.json(data ?? {}, { status: upstream.status });
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
