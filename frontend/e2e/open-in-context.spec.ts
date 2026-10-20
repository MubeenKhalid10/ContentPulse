import { expect, type Page, test } from "@playwright/test";

/**
 * A post opened from outside its section lands on the page for its current
 * step, and Back returns to the page it was opened from.
 */

const PASSWORD = "correct-horse-battery"; // same test-only value as backend/tests/conftest.py

async function signUp(page: Page) {
  await page.goto("/register");
  await page.getByLabel("Full name").fill("Olive Opener");
  await page.getByLabel("Work email").fill(`e2e-open-${Date.now()}@example.com`);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/onboarding/);
  await page.getByLabel("Organization name").fill("Opener Co");
  await page.getByRole("button", { name: "Create organization" }).click();
  await expect(page).toHaveURL(/\/dashboard/);
  await page.getByRole("button", { name: "Skip tour" }).click();
}

const POST = "00000000-0000-4000-8000-0000000000a1";
const REQUEST = "00000000-0000-4000-8000-0000000000a2";
const TASK = "00000000-0000-4000-8000-0000000000a3";
const TOPIC = "00000000-0000-4000-8000-0000000000a4";

function postDetail(status: string, designStatus: string | null = null) {
  return {
    id: POST,
    status,
    design_task: designStatus ? { id: TASK, status: designStatus } : null,
    review: { request_id: REQUEST, status: "pending" },
  };
}

for (const [status, design, target] of [
  ["draft", null, `/content/${POST}`],
  ["content_review", null, `/approvals/${REQUEST}`],
  ["design_in_progress", "in_progress", `/design/${TASK}`],
  ["changes_requested", "in_progress", `/design/${TASK}`],
  ["changes_requested", "submitted", `/content/${POST}`],
  ["final", "completed", `/approvals/${REQUEST}`],
] as const) {
  test(`a ${status} post opens on ${target.split("/")[1]}`, async ({ page }) => {
    await signUp(page);
    await page.route(`**/api/v1/content/${POST}`, (route) =>
      route.fulfill({ json: postDetail(status, design) }),
    );
    // Only the redirect is checked; the target page's own data isn't needed.
    await page.route(/\/api\/v1\/(approvals|design\/tasks)\/0000/, (route) =>
      route.fulfill({ status: 404, json: { detail: "not found" } }),
    );
    await page.goto(`/posts/${POST}?from=${encodeURIComponent(`/topics/${TOPIC}`)}`);
    await expect(page).toHaveURL(
      new RegExp(`${target}\\?from=${encodeURIComponent(`/topics/${TOPIC}`)}$`),
    );
  });
}

test("back returns to the page the post was opened from", async ({ page }) => {
  await signUp(page);
  await page.route(/\/api\/v1\/approvals\/0000/, (route) =>
    route.fulfill({ status: 404, json: { detail: "not found" } }),
  );
  await page.goto(`/approvals/${REQUEST}?from=${encodeURIComponent(`/topics/${TOPIC}`)}`);
  await expect(page.getByRole("link", { name: "Back to topic" })).toHaveAttribute(
    "href",
    `/topics/${TOPIC}`,
  );
});

test("back without a known origin goes to the section list", async ({ page }) => {
  await signUp(page);
  await page.route(/\/api\/v1\/approvals\/0000/, (route) =>
    route.fulfill({ status: 404, json: { detail: "not found" } }),
  );
  // An off-site `from` is ignored.
  await page.goto(`/approvals/${REQUEST}?from=${encodeURIComponent("//evil.example.com")}`);
  await expect(page.getByRole("link", { name: "Approvals" }).last()).toHaveAttribute(
    "href",
    "/approvals",
  );
});
