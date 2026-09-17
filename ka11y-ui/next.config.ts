import type { NextConfig } from "next";

// Origin of the Python service that stores audit image assets. The combined
// response points image_url at same-origin /api/v1/assets/{id}; these rewrites
// proxy those requests to Python so <img src={image_url}> loads in the browser
// (the browser cannot reach the internal "python" host directly).
const PYTHON_ORIGIN = process.env.PYTHON_ORIGIN ?? "http://python:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return [
      // OIDC sign-in flow. The browser must hit these directly (redirects to
      // the identity provider and back) and the session cookie has to be set
      // on *this* origin, so the whole /auth/* surface is proxied verbatim.
      { source: "/api/v1/auth/:path*", destination: `${PYTHON_ORIGIN}/api/v1/auth/:path*` },
      // Content-addressed asset store (current scheme)
      { source: "/api/v1/assets/:path*", destination: `${PYTHON_ORIGIN}/api/v1/assets/:path*` },
      // Legacy per-job image serving (fallback for older runs)
      { source: "/api/v1/combined/:jobId/image", destination: `${PYTHON_ORIGIN}/api/v1/combined/:jobId/image` },
    ];
  },
};

export default nextConfig;
