import type { NextConfig } from "next";

const API_URL = process.env.API_URL ?? "http://localhost:8000";

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
