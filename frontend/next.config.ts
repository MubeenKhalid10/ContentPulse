import type { NextConfig } from "next";

const API_URL = process.env.API_URL ?? "http://localhost:8000";

// On Vercel the API lives elsewhere (Render): fail the build rather than ship
// a site that proxies every request to localhost.
if (process.env.VERCEL && !process.env.API_URL) {
  throw new Error("Set API_URL in the Vercel project (Settings > Environment Variables) to the backend's URL.");
}

const isDev = process.env.NODE_ENV !== "production";

// Enforced: no framing (clickjacking of the approve buttons), no <base> or <object>
// tricks, forms post only to this site, and scripts, frames and network calls may only
// go to the origins below. Next's own inline bootstrap scripts still need
// 'unsafe-inline' (a nonce would make every page dynamic), so injected inline script is
// not blocked yet, but injected *external* scripts, exfiltration to other hosts and
// foreign frames are.
const CSP = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline' https://challenges.cloudflare.com${isDev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob: https:",
  "font-src 'self' data:",
  // Supabase auth, and presigned uploads straight to S3.
  `connect-src 'self' https://*.supabase.co wss://*.supabase.co https://*.amazonaws.com${isDev ? " ws://localhost:* ws://127.0.0.1:*" : ""}`,
  "media-src 'self' blob: https:",
  // Cloudflare Turnstile renders its challenge in an iframe.
  "frame-src https://challenges.cloudflare.com",
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "object-src 'none'",
  "form-action 'self'",
].join("; ");

const SECURITY_HEADERS = [
  { key: "Content-Security-Policy", value: CSP },
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
