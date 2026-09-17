/**
 * Client-side helpers for the OIDC session.
 *
 * All auth endpoints live on the Python API and are reached through the
 * `/api/v1/auth/*` rewrite in next.config.ts, so the browser talks to its own
 * origin and the session cookie (httpOnly, set by the API) stays first-party.
 */

export const SESSION_COOKIE = "ka11y_session";
export const LOGIN_URL = "/api/v1/auth/login";
export const LOGOUT_URL = "/api/v1/auth/logout";

/** Label for the sign-in button; the provider itself is configured server-side. */
export const AUTH_PROVIDER_LABEL =
  process.env.NEXT_PUBLIC_AUTH_PROVIDER_LABEL ?? "Google";

/** Build the URL that starts the sign-in flow. */
export function loginUrl(opts: { remember?: boolean; next?: string } = {}): string {
  const params = new URLSearchParams();
  params.set("remember", opts.remember ? "1" : "0");
  if (opts.next && opts.next.startsWith("/") && !opts.next.startsWith("//")) {
    params.set("next", opts.next);
  }
  return `${LOGIN_URL}?${params.toString()}`;
}

/**
 * The API answered 401: the cookie is missing, forged, or the session expired
 * server-side. The browser cannot delete an httpOnly cookie itself, so end the
 * session through the API (which clears it) and land on the login page.
 */
export async function redirectToLogin(reason: string = "session_expired"): Promise<void> {
  try {
    await fetch(LOGOUT_URL, { method: "POST", credentials: "same-origin" });
  } catch {
    // Best effort; the login page works either way.
  }
  const next = window.location.pathname + window.location.search;
  const params = new URLSearchParams({ error: reason, next });
  window.location.assign(`/login?${params.toString()}`);
}
