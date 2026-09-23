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
const SESSION_COOKIE = "ka11y_session";

/**
 * Cookies are scoped per host, so a session created on localhost is invisible
 * on 127.0.0.1 and vice versa. Fold the loopback IP onto "localhost" so local
 * use has one origin (and one cookie jar) whichever address was typed.
 */
const CANONICAL_LOCAL_HOST = "localhost";

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
  const hasSession = Boolean(request.cookies.get(SESSION_COOKIE)?.value);

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
  return res;
}

export const config = {
  // Everything except Next's own assets, so the host redirect covers /login
  // and /register as well as the gated areas.
  matcher: ["/((?!_next/|favicon.ico).*)"],
};
