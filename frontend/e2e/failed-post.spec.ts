import { expect, type Page, test } from "@playwright/test";

/** A post whose writing failed can be written again or deleted from the list. */

const PASSWORD = "correct-horse-battery"; // same test-only value as backend/tests/conftest.py
const now = new Date().toISOString();

async function signUp(page: Page) {
  await page.goto("/register");
  await page.getByLabel("Full name").fill("Fay Failed");
  await page.getByLabel("Work email").fill(`e2e-failed-${Date.now()}@example.com`);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/onboarding/);
  await page.getByLabel("Organization name").fill("Failed Co");
  await page.getByRole("button", { name: "Create organization" }).click();
  await expect(page).toHaveURL(/\/dashboard/);
  await page.getByRole("button", { name: "Skip tour" }).click();
}

test("a failed post offers Try again and Delete", async ({ page }) => {
  await signUp(page);
  const id = "00000000-0000-4000-8000-0000000000f1";
  const failed = {
    id,
    title: "Failed post",
    platform: "x",
    status: "draft",
    current_version: 0,
    hook: null,
    topic: null,
    content_strategy_id: null,
    variant_of_id: null,
    generation: {
      job_id: "00000000-0000-4000-8000-0000000000f2",
      kind: "generate",
      status: "failed",
      engine: "ai",
      error: "The model is unavailable.",
      created_at: now,
      completed_at: now,
    },
    created_at: now,
    updated_at: now,
  };
  let deleted = false;
  await page.route(/\/api\/v1\/content\?/, (route) =>
    route.fulfill({
      json: {
        items: deleted ? [] : [failed],
        total: deleted ? 0 : 1,
        counts: { drafts: deleted ? 0 : 1, changes: 0, design: 0, approval: 0, approved: 0, archived: 0, all: 1 },
      },
    }),
  );
  await page.route(`**/api/v1/content/${id}`, (route) => {
    if (route.request().method() !== "DELETE") return route.fallback();
    deleted = true;
    return route.fulfill({ status: 204 });
  });
  await page.goto("/content");
  const row = page.getByRole("listitem").filter({ hasText: "Failed post" }).last();
  await expect(row.getByText("Writing this post failed.")).toBeVisible();
  await expect(row.getByRole("button", { name: "Try again" })).toBeVisible();
  await row.getByRole("button", { name: "Delete" }).click();
  await expect(page.getByText("Failed post deleted")).toBeVisible();
  expect(deleted).toBe(true);
});
