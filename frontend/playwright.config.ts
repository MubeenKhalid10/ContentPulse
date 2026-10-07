import { defineConfig, devices } from "@playwright/test";

// Expects the API (localhost:8000) and web app (localhost:3000) to be running.
// The knowledge-base spec crawls a fixture site on 127.0.0.1:8088, so the API
// must be started with CRAWLER_ALLOW_PRIVATE_NETWORKS=true (dev/test only).
export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  // The specs share one API, and the trends spec runs live discovery and
  // analysis; in parallel on a busy laptop the others time out waiting for it.
  workers: Number(process.env.E2E_WORKERS ?? 1),
  reporter: "list",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
  },
  webServer: {
    command: "python -m http.server 8088 --bind 127.0.0.1 --directory e2e/fixtures/site",
    url: "http://127.0.0.1:8088/robots.txt",
    reuseExistingServer: true,
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
