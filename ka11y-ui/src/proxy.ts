import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * Route gate (Next 16 `proxy.ts`, the successor of middleware.ts).
 *
 * Presence of the session cookie is all that is checked here — it is cheap
 * and keeps signed-out visitors off the dashboard. Whether the session is
 * *valid* is decided by the Python API on every request; a stale cookie gets
 * a 401 there and `redirectToLogin()` in src/lib/auth.ts handles it.
 */
// "__Host-ka11y_session" on https, "ka11y_session" on http localhost (see
// src/lib/auth.ts). proxy.ts runs on the edge runtime, so the list is
// repeated here rather than imported.
const SESSION_COOKIE_NAMES = ["__Host-ka11y_session", "ka11y_session"];

/**
 * Cookies are scoped per host, so a session created on localhost is invisible
 * on 127.0.0.1 and vice versa. Fold the loopback IP onto "localhost" so local
 * use has one origin (and one cookie jar) whichever address was typed.
 */
const CANONICAL_LOCAL_HOST = "localhost";

// Mirrors the static CSP in next.config.ts, plus upgrade-insecure-requests,
// which is only safe once the document itself came over https (see the
// comment there). The TLS edge / ALB sets x-forwarded-proto.
const CSP_HTTPS =
  "frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'; upgrade-insecure-requests";

function servedOverHttps(request: NextRequest): boolean {
  const forwarded = request.headers.get("x-forwarded-proto");
  if (forwarded) return forwarded.split(",")[0].trim() === "https";
  return request.nextUrl.protocol === "https:";
}

export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;

  // Use the raw Host header: behind Docker's port mapping nextUrl reports the
  // server's own bind address, not what the browser typed.
  const host = request.headers.get("host") ?? "";
  if (host === "127.0.0.1" || host.startsWith("127.0.0.1:")) {
    const port = host.includes(":") ? host.slice(host.indexOf(":")) : "";
    const proto = request.headers.get("x-forwarded-proto") ?? "http";
    return NextResponse.redirect(`${proto}://${CANONICAL_LOCAL_HOST}${port}${pathname}${search}`, 308);
  }
  const hasSession = SESSION_COOKIE_NAMES.some((name) => Boolean(request.cookies.get(name)?.value));

  const gated = pathname.startsWith("/dashboard") || pathname.startsWith("/admin");
  if (gated && !hasSession) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.search = "";
    url.searchParams.set("next", pathname + search);
    return NextResponse.redirect(url);
  }
  const res = NextResponse.next();
  if (gated) {
    // Never let a browser or proxy replay a signed-in page after logout.
    res.headers.set("Cache-Control", "no-store, must-revalidate");
  }
  if (servedOverHttps(request)) res.headers.set("Content-Security-Policy", CSP_HTTPS);
  return res;
}

export const config = {
  // Everything except Next's own assets, so the host redirect covers /login
  // and /register as well as the gated areas.
  matcher: ["/((?!_next/|favicon.ico).*)"],
};
