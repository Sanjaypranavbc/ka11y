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

export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const hasSession = Boolean(request.cookies.get(SESSION_COOKIE)?.value);

  const gated = pathname.startsWith("/dashboard") || pathname.startsWith("/admin");
  if (gated && !hasSession) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.search = "";
    url.searchParams.set("next", pathname + search);
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/dashboard/:path*", "/admin/:path*"],
};
