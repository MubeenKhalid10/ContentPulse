import { expect, type Page, test } from "@playwright/test";

/**
 * One collection per discovery window: inside it, "Check for new trends"
 * collects nothing and says when the next discovery is due. The discovery
 * answers are served by the test (no internet, no provider calls).
 */

const PASSWORD = "correct-horse-battery"; // same test-only value as backend/tests/conftest.py

async function signUp(page: Page) {
  await page.goto("/register");
  await page.getByLabel("Full name").fill("Dara Window");
  await page.getByLabel("Work email").fill(`e2e-window-${Date.now()}@example.com`);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/onboarding/);
  await page.getByLabel("Organization name").fill("Window & Co");
  await page.getByRole("button", { name: "Create organization" }).click();
  await expect(page).toHaveURL(/\/dashboard/);
  await page.getByRole("button", { name: "Skip tour" }).click();
}

const minutesFromNow = (m: number) => new Date(Date.now() + m * 60_000).toISOString();

function windowBody(newTrends: number, lastAt: string) {
  return {
    background: true,
    last_discovery_at: lastAt,
    next_discovery_at: minutesFromNow(134),
    can_discover: false,
    new_trends: newTrends,
  };
}

function runBody(lastAt: string, created: number) {
  return {
    id: "00000000-0000-4000-8000-000000000001",
    status: "succeeded",
    trigger: "scheduled",
    sources: ["google_trends"],
    locations: [],
    results: {},
    warnings: [],
    items_collected: created,
    trends_created: created,
    trends_updated: 0,
    mentions_created: created,
    error: null,
    created_at: lastAt,
    started_at: lastAt,
    finished_at: lastAt,
  };
}

test("inside the discovery window the button reads stored trends and shows the wait", async ({
  page,
}) => {
  await signUp(page);
  // The last discovery finished before this page loaded the trends on screen.
  const lastAt = minutesFromNow(-46);
  const discoverCalls: string[] = [];
  await page.route("**/api/v1/trends/discovery", (route) =>
    route.request().resourceType() === "fetch"
      ? route.fulfill({ json: windowBody(12, lastAt) })
      : route.continue(),
  );
  await page.route("**/api/v1/trends/discover", (route) => {
    discoverCalls.push(route.request().method());
    return route.fulfill({
      status: 200,
      json: {
        started: false,
        run_id: runBody(lastAt, 12).id,
        status: "succeeded",
        run: runBody(lastAt, 12),
        window: windowBody(12, lastAt),
      },
    });
  });

  // The trends on screen must have loaded: the message compares against them.
  const listed = page.waitForResponse((r) => /\/api\/v1\/trends\?/.test(r.url()));
  await page.goto("/trends");
  await expect(page.getByText(/Next update in about 2h 1[34]m/)).toBeVisible();
  await listed;

  await page.getByRole("button", { name: "Check for new trends" }).first().click();
  await expect(page.getByText("No new trends found since the last discovery.")).toBeVisible();
  await expect(page.getByText(/New discovery will be available in 2h 1[34]m/)).toBeVisible();
  expect(discoverCalls).toEqual(["POST"]);
});

test("trends from a discovery that finished after the page loaded are announced", async ({
  page,
}) => {
  await signUp(page);
  await page.goto("/trends");
  await expect(page.getByRole("button", { name: "Check for new trends" }).first()).toBeVisible();

  // A scheduled discovery finished while the page was open.
  const lastAt = minutesFromNow(0.2);
  await page.route("**/api/v1/trends/discover", (route) =>
    route.fulfill({
      status: 200,
      json: {
        started: false,
        run_id: runBody(lastAt, 7).id,
        status: "succeeded",
        run: runBody(lastAt, 7),
        window: windowBody(7, lastAt),
      },
    }),
  );
  await page.getByRole("button", { name: "Check for new trends" }).first().click();
  await expect(page.getByText(/Showing the latest trends: 7 new from the/)).toBeVisible();
  await expect(page.getByText(/The next discovery runs in 2h 1[34]m/)).toBeVisible();
});
