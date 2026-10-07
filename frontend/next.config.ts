import type { NextConfig } from "next";

const API_URL = process.env.API_URL ?? "http://localhost:8000";

// On Vercel the API lives elsewhere (Render): fail the build rather than ship
// a site that proxies every request to localhost.
if (process.env.VERCEL && !process.env.API_URL) {
  throw new Error("Set API_URL in the Vercel project (Settings > Environment Variables) to the backend's URL.");
}

const nextConfig: NextConfig = {
  // Self-contained server bundle for the Docker image (frontend/Dockerfile).
  // Local `next dev` / `next start` are unaffected.
  output: process.env.NEXT_OUTPUT === "standalone" ? "standalone" : undefined,
  // The browser talks to the FastAPI backend through this same origin, so the
  // httpOnly session cookie is first-party and no CORS is needed.
  async rewrites() {
    return [{ source: "/api/v1/:path*", destination: `${API_URL}/api/v1/:path*` }];
  },
};

export default nextConfig;
