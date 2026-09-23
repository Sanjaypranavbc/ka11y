import { cookies } from "next/headers";

/**
 * Server-side view of the signed-in user, for layouts and server components.
 *
 * Calls the Python API directly (the browser-facing rewrite is not available
 * inside server components) and forwards the browser's session cookie. Any
 * failure — no cookie, expired session, API down — resolves to null so the
 * caller can decide between 404, redirect, or a public fallback.
 */
const PYTHON_ORIGIN = process.env.PYTHON_ORIGIN ?? "http://python:8000";
// "__Host-ka11y_session" on https, "ka11y_session" on http localhost; the
// API only reads the name it set, so the matching one is forwarded verbatim.
const SESSION_COOKIE_NAMES = ["__Host-ka11y_session", "ka11y_session"];

export type ServerUser = {
  user_id: string | null;
  email: string | null;
  name: string | null;
  organization_id: string | null;
  role: string | null;
  anonymous: boolean;
  is_admin: boolean;
};

export async function getServerUser(): Promise<ServerUser | null> {
  const jar = await cookies();
  const name = SESSION_COOKIE_NAMES.find((n) => jar.get(n)?.value);
  const session = name ? jar.get(name)?.value : undefined;
  if (!name || !session) return null;
  try {
    const res = await fetch(`${PYTHON_ORIGIN}/api/v1/auth/me`, {
      headers: { cookie: `${name}=${session}` },
      cache: "no-store",
    });
    if (!res.ok) return null;
    return (await res.json()) as ServerUser;
  } catch {
    return null;
  }
}
