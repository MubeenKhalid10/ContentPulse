import { expect, type Page, test } from "@playwright/test";

/**
 * While data is on its way the page says so. It never shows what would be true
 * if the data were empty: a plan as still unwritten, or "no posts".
 */

const PASSWORD = "correct-horse-battery"; // same test-only value as backend/tests/conftest.py

async function signUp(page: Page) {
  await page.goto("/register");
  await page.getByLabel("Full name").fill("Lena Loader");
  await page.getByLabel("Work email").fill(`e2e-loading-${Date.now()}@example.com`);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/onboarding/);
  await page.getByLabel("Organization name").fill("Loading Co");
  await page.getByRole("button", { name: "Create organization" }).click();
  await expect(page).toHaveURL(/\/dashboard/);
  await page.getByRole("button", { name: "Skip tour" }).click();
}

const TREND = "00000000-0000-4000-8000-0000000000b1";
const TOPIC = "00000000-0000-4000-8000-0000000000b2";
const PLAN = "00000000-0000-4000-8000-0000000000b3";
const POST = "00000000-0000-4000-8000-0000000000b4";
const NOW = new Date().toISOString();

const trend = {
  id: TREND,
  topic: "Oct 2026",
  title: "Oct 2026",
  status: "shortlisted",
  opportunity_score: 25,
  mention_count: 15,
  sources: ["reddit"],
  locations: [],
  relevance_level: "not_relevant",
  relevance_overridden: false,
  last_seen_at: NOW,
  alignment: { classification: "not_relevant", possible_angles: [] },
  signals: {},
  mentions: [],
  analysis: null,
  topic_id: TOPIC,
};

const topic = {
  id: TOPIC,
  title: "Oct 2026",
  status: "shortlisted",
  strategies: [
    {
      id: PLAN,
      topic_id: TOPIC,
      platform: "blog",
      status: "draft",
      source: "manual",
      core_message: "A plan that already has its post",
      objective: "awareness",
      target_audience: "Founders",
      tone: "informative",
      post_type: "article",
      created_at: NOW,
      updated_at: NOW,
    },
  ],
};

const page1 = (items: unknown[]) => ({ items, total: items.length, counts: {} });
const post = {
  id: POST,
  title: "The written post",
  platform: "blog",
  status: "draft",
  current_version: 1,
  hook: "Its opening line",
  topic: { id: TOPIC, title: "Oct 2026", status: "shortlisted" },
  content_strategy_id: PLAN,
  variant_of_id: null,
  generation: null,
  changes_scope: null,
  created_at: NOW,
  updated_at: NOW,
};

test("a plan isn't offered as unwritten until its posts have loaded", async ({ page }) => {
  await signUp(page);
  let release = () => {};
  const held = new Promise<void>((resolve) => (release = resolve));
  await page.route(`**/api/v1/trends/${TREND}`, (route) => route.fulfill({ json: trend }));
  await page.route(`**/api/v1/topics/${TOPIC}**`, (route) => route.fulfill({ json: topic }));
  await page.route(/\/api\/v1\/content\?.*topic_id=/, async (route) => {
    await held;
    await route.fulfill({ json: page1([post]) });
  });

  await page.goto(`/trends/${TREND}`);
  await expect(page.getByText("Loading post plans…")).toBeVisible();
  await expect(page.getByText("Loading generated posts…")).toBeVisible();
  await expect(page.getByText("A plan that already has its post")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Create plan" })).toHaveCount(0);

  release();
  await expect(page.getByRole("link", { name: "The written post" })).toBeVisible();
  await expect(page.getByText("Every plan has a post.")).toBeVisible();
  await expect(page.getByText("A plan that already has its post")).toHaveCount(0);
  await expect(page.getByText(/^Loading .*…$/)).toHaveCount(0);
});

test("if the posts can't load the page says so and offers a retry", async ({ page }) => {
  await signUp(page);
  let fail = true;
  await page.route(`**/api/v1/trends/${TREND}`, (route) => route.fulfill({ json: trend }));
  await page.route(`**/api/v1/topics/${TOPIC}**`, (route) => route.fulfill({ json: topic }));
  await page.route(/\/api\/v1\/content\?.*topic_id=/, (route) =>
    fail
      ? route.fulfill({ status: 404, json: { error: { code: "NOT_FOUND", message: "Gone." } } })
      : route.fulfill({ json: page1([post]) }),
  );

  await page.goto(`/trends/${TREND}`);
  await expect(page.getByText(/Couldn't check which plans/)).toBeVisible();
  await expect(page.getByText("A plan that already has its post")).toHaveCount(0);

  fail = false;
  await page.getByRole("button", { name: "Retry" }).first().click();
  await expect(page.getByRole("link", { name: "The written post" })).toBeVisible();
});

test("changing a filter shows loading, not the previous results dimmed", async ({ page }) => {
  await signUp(page);
  let release = () => {};
  const held = new Promise<void>((resolve) => (release = resolve));
  await page.route(/\/api\/v1\/content\?/, async (route) => {
    if (new URL(route.request().url()).searchParams.get("q")) {
      await held;
      await route.fulfill({ json: page1([]) });
    } else {
      await route.fulfill({ json: page1([post]) });
    }
  });

  await page.goto("/content");
  const row = page.getByText("The written post").first();
  await expect(row).toBeVisible();
  await page.getByRole("searchbox").fill("nothing like this");
  await expect(page.getByText("Loading posts…")).toBeVisible();
  await expect(row).toHaveCount(0);

  release();
  await expect(page.getByText("Loading posts…")).toHaveCount(0);
});
