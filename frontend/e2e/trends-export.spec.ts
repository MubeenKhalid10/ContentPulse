import { readFile } from "node:fs/promises";

import { expect, type Page, test } from "@playwright/test";

/**
 * Admin-only "Download Trends — Last 7 Days". The download and the role
 * checks hit the real API; only the loading/error test stubs the export.
 */

const PASSWORD = "correct-horse-battery"; // same test-only value as backend/tests/conftest.py
const BUTTON = "Download Trends — Last 7 Days";
const HEADER = "Trend,Category,Keywords,Sources,Mentions,Opportunity score,Relevance,Status,First seen,Last seen";

async function signUp(page: Page, orgName: string) {
  await page.goto("/register");
  await page.getByLabel("Full name").fill("Ada Export");
  await page.getByLabel("Work email").fill(`e2e-export-${Date.now()}@example.com`);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/onboarding/);
  await page.getByLabel("Organization name").fill(orgName);
  await page.getByRole("button", { name: "Create organization" }).click();
  await expect(page).toHaveURL(/\/dashboard/);
  await page.getByRole("button", { name: "Skip tour" }).click();
}

test("an admin downloads the seven-day CSV for the selected organization", async ({ page }) => {
  await signUp(page, "Export & Co");
  // The page asks only for trends seen in the last 7 days.
  const listed = page.waitForRequest((r) => /\/api\/v1\/trends\?.*seen_within_days=7/.test(r.url()));
  await page.goto("/trends");
  await listed;

  await expect(page.getByText("Export & Co", { exact: false }).first()).toBeVisible();
  // The export sits at the top, above the discovery sources strip.
  const exportTop = (await page.getByRole("button", { name: BUTTON }).boundingBox())!.y;
  const sourcesTop = (await page.getByRole("region", { name: "Discovery sources" }).boundingBox())!.y;
  expect(exportTop).toBeLessThan(sourcesTop);
  const range = page.getByTestId("export-range");
  await expect(range).toContainText(/Trends last seen from .+\(UTC[+-]\d{2}:\d{2}\) up to .+\(UTC[+-]\d{2}:\d{2}\), \S+ time/);

  const downloading = page.waitForEvent("download");
  await page.getByRole("button", { name: BUTTON }).click();
  const download = await downloading;
  expect(download.suggestedFilename()).toMatch(
    /^contentpulse-trends_export-co[a-z0-9-]*_\d{8}T\d{6}[+-]\d{4}_to_\d{8}T\d{6}[+-]\d{4}\.csv$/,
  );
  const text = await readFile((await download.path())!, "utf-8");
  // A new organization has no trends: a valid CSV with only the headers.
  expect(text).toBe(`﻿${HEADER}\r\n`);
  await expect(page.getByRole("status").filter({ hasText: "the CSV has only the column headers" })).toBeVisible();
});

test("a creator sees no export and the API refuses it", async ({ page, browser }) => {
  await signUp(page, "Export Team");
  const me = await (await page.request.get("/api/v1/auth/me")).json();
  const invite = await page.request.post(`/api/v1/organizations/${me.organization_id}/invitations`, {
    data: { email: `e2e-export-creator-${Date.now()}@example.com`, role: "creator" },
  });
  expect(invite.status()).toBe(201);
  const token = (await invite.json()).invite_url.split("/").pop();

  const context = await browser.newContext();
  const creator = await context.newPage();
  const accepted = await creator.request.post("/api/v1/auth/invites/accept", {
    data: { token, full_name: "Cora Creator", password: PASSWORD },
  });
  expect(accepted.status()).toBe(200);
  await creator.goto("/trends");
  await expect(creator.getByRole("heading", { name: "Find trends" })).toBeVisible();
  await expect(creator.getByRole("button", { name: BUTTON })).toHaveCount(0);

  const resp = await creator.request.get("/api/v1/trends/export.csv");
  expect(resp.status()).toBe(403);
  expect(resp.headers()["content-type"]).not.toContain("text/csv");
  await context.close();
});

test("the button shows progress, blocks double clicks and reports failures", async ({ page }) => {
  await signUp(page, "Export Errors");
  let calls = 0;
  let release: () => void = () => {};
  const held = new Promise<void>((resolve) => (release = resolve));
  await page.route("**/api/v1/trends/export.csv", async (route) => {
    calls += 1;
    await held;
    await route.fulfill({
      status: 500,
      json: { error: { code: "INTERNAL_ERROR", message: "Something went wrong on our side." } },
    });
  });
  await page.goto("/trends");
  const button = page.getByRole("button", { name: BUTTON });
  await expect(button).toBeEnabled();
  await button.click();

  const busy = page.getByRole("button", { name: "Preparing CSV…" });
  await expect(busy).toBeDisabled();
  await busy.click({ force: true });
  release();
  await expect(page.getByText("The export failed: Something went wrong on our side.")).toBeVisible();
  await expect(button).toBeEnabled();
  expect(calls).toBe(1);
});
