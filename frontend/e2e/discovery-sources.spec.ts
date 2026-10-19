import { expect, type Page, test } from "@playwright/test";

/**
 * Discovery Sources: an admin turns sources on and off for their own
 * organization's feed. No internet needed: nothing here runs discovery.
 */

const PASSWORD = "correct-horse-battery"; // same test-only value as backend/tests/conftest.py
const SHOTS = process.env.E2E_SCREENSHOTS;

async function signUp(page: Page) {
  await page.goto("/register");
  await page.getByLabel("Full name").fill("Dara Sources");
  await page.getByLabel("Work email").fill(`e2e-sources-${Date.now()}@example.com`);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/onboarding/);
  await page.getByLabel("Organization name").fill("Feed & Co");
  await page.getByRole("button", { name: "Create organization" }).click();
  await expect(page).toHaveURL(/\/dashboard/);
  await page.getByRole("button", { name: "Skip tour" }).click();
}

test("toggle discovery sources, persist them and surface save errors", async ({ page }) => {
  await signUp(page);
  await page.goto("/trends/sources");

  await expect(page.getByRole("heading", { name: "Discovery Sources", level: 1 })).toBeVisible();
  await expect(
    page.getByText("Choose which sources contribute trends to your discovery feed."),
  ).toBeVisible();
  await expect(page.getByText(/doesn.t stop global collection/)).toBeVisible();

  const reddit = page.getByRole("switch", { name: "Include Reddit in discovery feed" });
  await expect(reddit).toBeChecked();
  if (SHOTS) {
    await page.screenshot({ path: `${SHOTS}/discovery-sources.png`, fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: `${SHOTS}/discovery-sources-mobile.png`, fullPage: true });
    await page.setViewportSize({ width: 1280, height: 800 });
  }

  // Turn it off: saved, announced, and still off after a reload.
  await reddit.click();
  await expect(page.getByText("Reddit turned off for your discovery feed").first()).toBeVisible();
  await expect(reddit).not.toBeChecked();
  await page.reload();
  await expect(
    page.getByRole("switch", { name: "Include Reddit in discovery feed" }),
  ).not.toBeChecked();

  // A failed save reports the error and leaves the saved state as it was.
  await page.route("**/trends/sources/hacker_news", (route) =>
    route.request().method() === "PATCH"
      ? route.fulfill({
          status: 500,
          contentType: "application/json",
          body: JSON.stringify({
            error: { code: "INTERNAL_ERROR", message: "Something went wrong." },
          }),
        })
      : route.continue(),
  );
  const hn = page.getByRole("switch", { name: "Include Hacker News in discovery feed" });
  await expect(hn).toBeChecked();
  await hn.click();
  await expect(page.getByText(/Couldn't update Hacker News/).first()).toBeVisible();
  await expect(hn).toBeChecked();
  await page.unroute("**/trends/sources/hacker_news");

  // Turning Reddit back on is persisted too.
  const redditAgain = page.getByRole("switch", { name: "Include Reddit in discovery feed" });
  await redditAgain.click();
  await expect(page.getByText("Reddit turned on for your discovery feed").first()).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("switch", { name: "Include Reddit in discovery feed" }),
  ).toBeChecked();
});

test("a load failure shows a retry", async ({ page }) => {
  await signUp(page);
  let fail = true;
  // Only the API call: the page itself also lives at /trends/sources.
  await page.route("**/trends/sources", (route) =>
    fail && route.request().resourceType() === "fetch"
      ? route.fulfill({
          status: 503,
          contentType: "application/json",
          body: JSON.stringify({ error: { code: "UNAVAILABLE", message: "API unavailable." } }),
        })
      : route.continue(),
  );
  await page.goto("/trends/sources");
  await expect(page.getByText("Couldn't load sources")).toBeVisible({ timeout: 20_000 });
  fail = false;
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(
    page.getByRole("switch", { name: "Include Google News in discovery feed" }),
  ).toBeVisible();
});

test("background updates are a single on/off switch on Trends", async ({ page }) => {
  await signUp(page);
  await page.goto("/trends");
  const background = page.getByRole("switch", { name: "Update trends in the background" });
  await expect(background).toBeChecked();
  await expect(page.getByText(/New trends arrive automatically \(every 3 hours\)/)).toBeVisible();
  await expect(page.getByRole("combobox", { name: /how often/i })).toHaveCount(0);
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/trends-background.png` });

  await background.click();
  await expect(page.getByText("Trends will update only when you ask")).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("switch", { name: "Update trends in the background" }),
  ).not.toBeChecked();

  // The Settings page shows the same choice.
  await page.goto("/organization/content-setup");
  await expect(
    page.getByRole("switch", { name: "Update trends in the background" }),
  ).not.toBeChecked();
});
