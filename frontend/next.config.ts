import type { NextConfig } from "next";

const API_URL = process.env.API_URL ?? "http://localhost:8000";

// On Vercel the API lives elsewhere (Render): fail the build rather than ship
// a site that proxies every request to localhost.
if (process.env.VERCEL && !process.env.API_URL) {
  throw new Error("Set API_URL in the Vercel project (Settings > Environment Variables) to the backend's URL.");
}

const isDev = process.env.NODE_ENV !== "production";

// Enforced now: no framing (clickjacking of the approve buttons), no <base>
// or <object> tricks, forms post only to this site.
const ENFORCED_CSP = ["frame-ancestors 'none'", "base-uri 'self'", "object-src 'none'", "form-action 'self'"].join("; ");

// Report-only for now: the full policy a nonce-based setup would enforce.
// Next's own inline scripts need 'unsafe-inline' until nonces are wired in
// (that makes every page dynamic), so this only logs what it would block.
// Check the browser console for violations, then tighten and enforce it.
const REPORT_ONLY_CSP = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob: https:",
  "font-src 'self' data:",
  // Supabase auth, and presigned uploads straight to S3.
  "connect-src 'self' https://*.supabase.co https://*.amazonaws.com",
  "media-src 'self' blob: https:",
  ENFORCED_CSP,
].join("; ");

const SECURITY_HEADERS = [
  { key: "Content-Security-Policy", value: ENFORCED_CSP },
  { key: "Content-Security-Policy-Report-Only", value: REPORT_ONLY_CSP },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  // HTTPS only (browsers ignore it over HTTP); not for local development.
  ...(isDev ? [] : [{ key: "Strict-Transport-Security", value: "max-age=31536000" }]),
];

const nextConfig: NextConfig = {
  // Self-contained server bundle for the Docker image (frontend/Dockerfile).
  // Local `next dev` / `next start` are unaffected.
  output: process.env.NEXT_OUTPUT === "standalone" ? "standalone" : undefined,
  // The browser talks to the FastAPI backend through this same origin, so the
  // httpOnly session cookie is first-party and no CORS is needed.
  async headers() {
    // Pages only: /api/* responses (including file downloads) keep the backend's own headers.
    return [{ source: "/((?!api/).*)", headers: SECURITY_HEADERS }];
  },
  async rewrites() {
    return [{ source: "/api/v1/:path*", destination: `${API_URL}/api/v1/:path*` }];
  },
};

export default nextConfig;
