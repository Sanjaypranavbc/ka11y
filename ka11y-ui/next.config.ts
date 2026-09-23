import type { NextConfig } from "next";

// Origin of the Python service that stores audit image assets. The combined
// response points image_url at same-origin /api/v1/assets/{id}; these rewrites
// proxy those requests to Python so <img src={image_url}> loads in the browser
// (the browser cannot reach the internal "python" host directly).
const PYTHON_ORIGIN = process.env.PYTHON_ORIGIN ?? "http://python:8000";

// Transport hardening. TLS is terminated in front of the container (ALB,
// Caddy, nginx); the headers below make the browser hold the line after that:
//   - HSTS: a year, so a return visit never starts on plain http. Sent
//     unconditionally — browsers ignore it on http responses, so localhost is
//     unaffected. Set KA11Y_HSTS_PRELOAD=1 once the apex is submitted to
//     hstspreload.org (it then covers every sub-domain, so be sure).
//   - CSP: no framing by anyone, no <base> hijack, forms only post to us, no
//     plugins, and every http sub-resource is upgraded. Script/style sources
//     are left to Next (a nonce-based policy needs per-request middleware and
//     is a follow-up); frame-ancestors is the part the Kao sheet asks for.
//   - The rest close off MIME sniffing, referrer leakage, cross-origin window
//     handles and powerful browser features the app never uses.
const HSTS = `max-age=31536000${process.env.KA11Y_HSTS_PRELOAD === "1" ? "; includeSubDomains; preload" : ""}`;
const CSP = [
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
  "upgrade-insecure-requests",
].join("; ");
const SECURITY_HEADERS = [
  { key: "Strict-Transport-Security", value: HSTS },
  { key: "Content-Security-Policy", value: CSP },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
  {
    key: "Permissions-Policy",
    value: "accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=(), interest-cohort=(), browsing-topics=()",
  },
];

const nextConfig: NextConfig = {
  output: "standalone",
  // Never advertise the framework; one less fingerprint for a scanner.
  poweredByHeader: false,
  async headers() {
    return [{ source: "/:path*", headers: SECURITY_HEADERS }];
  },
  async rewrites() {
    return [
      // OIDC sign-in flow. The browser must hit these directly (redirects to
      // the identity provider and back) and the session cookie has to be set
      // on *this* origin, so the whole /auth/* surface is proxied verbatim.
      { source: "/api/v1/auth/:path*", destination: `${PYTHON_ORIGIN}/api/v1/auth/:path*` },
      // Content-addressed asset store (current scheme)
      { source: "/api/v1/assets/:path*", destination: `${PYTHON_ORIGIN}/api/v1/assets/:path*` },
      // Admin console data + live event stream, and per-audit artifact/report
      // downloads. Same-origin so the session cookie travels with them.
      { source: "/api/v1/admin/:path*", destination: `${PYTHON_ORIGIN}/api/v1/admin/:path*` },
      { source: "/api/v1/audits/:path*", destination: `${PYTHON_ORIGIN}/api/v1/audits/:path*` },
      // Legacy per-job image serving (fallback for older runs)
      { source: "/api/v1/combined/:jobId/image", destination: `${PYTHON_ORIGIN}/api/v1/combined/:jobId/image` },
    ];
  },
};

export default nextConfig;
