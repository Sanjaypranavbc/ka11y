/**
 * Client-side helpers for sign-in.
 *
 * All auth endpoints live on the Python API and are reached through the
 * `/api/v1/auth/*` rewrite in next.config.ts, so the browser talks to its own
 * origin and the session cookie (httpOnly, set by the API) stays first-party.
 *
 * Two ways in, both ending in the same session cookie:
 *   - e-mail + password: POST /auth/password/login | /auth/password/register
 *   - OIDC (Google by default): GET /auth/login → provider → /auth/callback
 */

/**
 * The API names the session cookie "__Host-ka11y_session" on https (the
 * prefix makes the browser enforce Secure + Path=/ + no Domain) and plain
 * "ka11y_session" on http localhost. Both names are checked everywhere the UI
 * looks for a session; the first match wins.
 */
export const SESSION_COOKIE_NAMES = ["__Host-ka11y_session", "ka11y_session"] as const;
/** @deprecated use SESSION_COOKIE_NAMES — kept for older imports. */
export const SESSION_COOKIE = SESSION_COOKIE_NAMES[1];
export const LOGIN_URL = "/api/v1/auth/login";
export const LOGOUT_URL = "/api/v1/auth/logout";
export const CONFIG_URL = "/api/v1/auth/config";
const PASSWORD_LOGIN_URL = "/api/v1/auth/password/login";
const PASSWORD_REGISTER_URL = "/api/v1/auth/password/register";

/** Label for the OIDC button; the provider itself is configured server-side. */
export const AUTH_PROVIDER_LABEL =
  process.env.NEXT_PUBLIC_AUTH_PROVIDER_LABEL ?? "Google";

export type AuthConfig = {
  configured: boolean;
  disabled: boolean;
  provider: string;
  oidc: boolean;
  password_login: boolean;
  registration: boolean;
};

/** What the login page assumes until /auth/config answers. */
export const DEFAULT_AUTH_CONFIG: AuthConfig = {
  configured: true,
  disabled: false,
  provider: "google",
  oidc: false,
  password_login: true,
  registration: true,
};

export async function fetchAuthConfig(): Promise<AuthConfig> {
  try {
    const res = await fetch(CONFIG_URL, { credentials: "same-origin", cache: "no-store" });
    if (!res.ok) return DEFAULT_AUTH_CONFIG;
    return { ...DEFAULT_AUTH_CONFIG, ...((await res.json()) as Partial<AuthConfig>) };
  } catch {
    return DEFAULT_AUTH_CONFIG;
  }
}

/** Build the URL that starts the OIDC sign-in flow. */
export function loginUrl(opts: { remember?: boolean; next?: string } = {}): string {
  const params = new URLSearchParams();
  params.set("remember", opts.remember ? "1" : "0");
  if (isSafeNext(opts.next)) params.set("next", opts.next as string);
  return `${LOGIN_URL}?${params.toString()}`;
}

/** Where a sign-in lands when no safe `next` was requested (mirrors KA11Y_POST_LOGIN_URL). */
export const POST_LOGIN_PATH = "/dashboard/new-audit";

function isSafeNext(next?: string): boolean {
  return Boolean(next && next.startsWith("/") && !next.startsWith("//"));
}

/** A rejected password sign-in / registration; `code` maps to t.login.errors. */
export class AuthApiError extends Error {
  code: string;
  status: number;
  constructor(code: string, status: number) {
    super(code);
    this.code = code;
    this.status = status;
  }
}

async function postAuth(url: string, body: Record<string, unknown>): Promise<{ next: string }> {
  let res: Response;
  try {
    res = await fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new AuthApiError("network", 0);
  }
  if (!res.ok) {
    let code = "generic";
    try {
      const data = (await res.json()) as { error?: string };
      if (data.error) code = data.error;
    } catch {
      // non-JSON error body: keep the generic code
    }
    if (res.status === 503) code = "login_disabled";
    throw new AuthApiError(code, res.status);
  }
  const data = (await res.json()) as { next?: string };
  return { next: isSafeNext(data.next) ? (data.next as string) : POST_LOGIN_PATH };
}

export function passwordLogin(opts: {
  email: string;
  password: string;
  remember?: boolean;
  next?: string;
}): Promise<{ next: string }> {
  return postAuth(PASSWORD_LOGIN_URL, {
    email: opts.email,
    password: opts.password,
    remember: Boolean(opts.remember),
    next: isSafeNext(opts.next) ? opts.next : undefined,
  });
}

export function registerAccount(opts: {
  email: string;
  password: string;
  name?: string;
  remember?: boolean;
  next?: string;
}): Promise<{ next: string }> {
  return postAuth(PASSWORD_REGISTER_URL, {
    email: opts.email,
    password: opts.password,
    name: opts.name || undefined,
    remember: Boolean(opts.remember),
    next: isSafeNext(opts.next) ? opts.next : undefined,
  });
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
