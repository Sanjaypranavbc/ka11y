/**
 * Forwarding headers to copy onto server-side calls from this Next server to
 * the Python API.
 *
 * The API decides "is this request https?" from what the proxy in front of it
 * says (X-Forwarded-Proto, set by the ALB / Caddy edge and carried through by
 * Next — it fills x-forwarded-* in on every incoming request). A route
 * handler's or server component's own fetch() to http://python:8000 starts a
 * brand-new request with none of that, so with the https redirect on the API
 * answered 308 → https://python:8000/…, which nothing serves: sign-in landed
 * back on /login and audits reported "Unable to reach the WCAG analysis
 * service". Passing the browser's forwarding headers along makes the
 * server-side hop look like what it is: the same https request, one hop on.
 */
export const FORWARDED_HEADER_NAMES = [
  "x-forwarded-proto",
  "x-forwarded-host",
  "x-forwarded-for",
] as const;

type HeaderSource = { get(name: string): string | null };

/** The forwarding headers present on `source` (a Request's headers or `await headers()`). */
export function forwardedHeaders(source: HeaderSource): Record<string, string> {
  const out: Record<string, string> = {};
  for (const name of FORWARDED_HEADER_NAMES) {
    const value = source.get(name);
    if (value) out[name] = value;
  }
  return out;
}
