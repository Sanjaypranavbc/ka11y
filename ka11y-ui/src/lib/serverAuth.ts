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
const SESSION_COOKIE = "ka11y_session";

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
  const session = jar.get(SESSION_COOKIE)?.value;
  if (!session) return null;
  try {
    const res = await fetch(`${PYTHON_ORIGIN}/api/v1/auth/me`, {
      headers: { cookie: `${SESSION_COOKIE}=${session}` },
      cache: "no-store",
    });
    if (!res.ok) return null;
    return (await res.json()) as ServerUser;
  } catch {
    return null;
  }
}
