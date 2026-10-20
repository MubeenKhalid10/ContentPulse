import { expect, type Page, test } from "@playwright/test";

/**
 * Tabs and status tags say which stage they are about (content vs design
 * approval), so they make sense without relying on color.
 */

const PASSWORD = "correct-horse-battery"; // same test-only value as backend/tests/conftest.py
const now = new Date().toISOString();

async function signUp(page: Page) {
  await page.goto("/register");
  await page.getByLabel("Full name").fill("Lou Labels");
  await page
    .getByLabel("Work email")
    .fill(`e2e-labels-${Date.now()}@example.com`);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/onboarding/);
  await page.getByLabel("Organization name").fill("Labels Co");
  await page.getByRole("button", { name: "Create organization" }).click();
  await expect(page).toHaveURL(/\/dashboard/);
  await page.getByRole("button", { name: "Skip tour" }).click();
}

const tabNames = async (page: Page) =>
  (await page.getByRole("tab").allTextContents()).map((t) =>
    t.replace(/\d+$/, "").trim(),
  );

test("content, design and approval tabs name their stage", async ({ page }) => {
  await signUp(page);

  // Content: content stages only (design and publishing have their own pages).
  // A brand-new organization sees a getting-started message instead of tabs,
  // so the list reports one post.
  const counts = {
    drafts: 1,
    design: 0,
    approval: 0,
    approved: 0,
    archived: 0,
    all: 1,
  };
  const draft = {
    id: "00000000-0000-4000-8000-0000000000d1",
    title: "A draft",
    platform: "linkedin",
    status: "draft",
    current_version: 1,
    hook: "Hook",
    topic: null,
    content_strategy_id: null,
    variant_of_id: null,
    generation: null,
    created_at: now,
    updated_at: now,
  };
  await page.route(/\/api\/v1\/content\?/, (route) =>
    route.fulfill({ json: { items: [draft], total: 1, counts } }),
  );
  await page.goto("/content");
  await expect(page.getByRole("tab", { name: /^Draft posts/ })).toBeVisible();
  // No Archived tab (there is no archiving).
  expect(await tabNames(page)).toEqual([
    "Draft posts",
    "Changes requested",
    "Approval status",
  ]);

  // Topics: no Archived tab either.
  const topic = {
    id: "00000000-0000-4000-8000-0000000000d4",
    trend_id: null,
    title: "A topic",
    summary: null,
    relevance_level: null,
    matched_services: [],
    recommended_platforms: [],
    status: "new",
    opportunity_score: null,
    strategy_count: 0,
    approved_strategy_count: 0,
    created_at: now,
    updated_at: now,
  };
  await page.route(/\/api\/v1\/topics\?/, (route) =>
    route.fulfill({
      json: {
        items: [topic],
        total: 1,
        counts: { new: 1, reviewed: 0, shortlisted: 0, rejected: 0, archived: 0 },
      },
    }),
  );
  await page.goto("/topics");
  await expect(page.getByRole("tab", { name: /^To review/ })).toBeVisible();
  await expect(page.getByRole("tab", { name: /Archived/ })).toHaveCount(0);

  // Design and approvals also hide their tabs when empty, so each list
  // reports one item.
  const task = {
    id: "00000000-0000-4000-8000-0000000000d2",
    status: "submitted",
    format: "single_image",
    dimensions: null,
    headline: null,
    post: {
      id: draft.id,
      title: "A post",
      platform: "linkedin",
      status: "pending_approval",
      current_version: 1,
      topic_title: null,
    },
    assignee: null,
    creative_versions: 1,
    source: "rules",
    created_at: now,
    updated_at: now,
    submitted_at: now,
  };
  await page.route(/\/api\/v1\/design\/tasks\?/, (route) =>
    route.fulfill({
      json: {
        items: [task],
        total: 1,
        counts: { todo: 0, submitted: 1, done: 0, cancelled: 0, all: 1 },
      },
    }),
  );
  await page.goto("/design");
  await expect(
    page.getByRole("tab", { name: /^Designs to create/ }),
  ).toBeVisible();
  await expect(page.getByRole("list", { name: "Design tasks" })).toBeVisible();
  expect(await tabNames(page)).toEqual([
    "Designs to create",
    "Changes requested",
    "Approval status",
  ]);
  await expect(page.getByRole("list", { name: "Design tasks" })).toContainText(
    "Waiting for design approval",
  );

  await page.route(/\/api\/v1\/approvals\?/, (route) => {
    const stage =
      new URL(route.request().url()).searchParams.get("stage") === "design"
        ? "design"
        : "copy";
    const approval = {
      id: "00000000-0000-4000-8000-0000000000d3",
      stage,
      status: "pending",
      round: 1,
      post: {
        id: draft.id,
        title: "A post",
        platform: "linkedin",
        status: "content_review",
        current_version: 1,
      },
      topic_title: null,
      post_version: 1,
      creative_version: stage === "design" ? 1 : null,
      preview_url: null,
      submitted_by: null,
      reviewer: null,
      comment_count: 0,
      created_at: now,
      reviewed_at: null,
    };
    return route.fulfill({
      json: {
        items: [approval],
        total: 1,
        counts: {
          pending: 1,
          reviewed: 0,
          approved: 0,
          changes_requested: 0,
          rejected: 0,
          all: 1,
        },
        stage_pending: { copy: 1, design: 1 },
      },
    });
  });
  await page.goto("/approvals");
  const queue = page.getByRole("list", { name: "Approvals" });
  await expect(queue).toContainText("Waiting for content approval");
  expect(await tabNames(page)).toEqual([
    "Content approval",
    "Design approval",
    "Ready to post",
  ]);
  await page.getByRole("tab", { name: /Design approval/ }).click();
  await expect(queue).toContainText("Waiting for design approval");
  expect(await tabNames(page)).toEqual([
    "Content approval",
    "Design approval",
    "Ready to post",
  ]);
});

test("a post waiting for content approval shows one status tag", async ({
  page,
}) => {
  await signUp(page);
  const id = "00000000-0000-4000-8000-0000000000dd";
  const post = {
    id,
    title: "Development company",
    platform: "linkedin",
    status: "content_review",
    current_version: 1,
    hook: "Hook",
    topic: null,
    content_strategy_id: null,
    variant_of_id: null,
    generation: null,
    created_at: now,
    updated_at: now,
    current: {
      id: "00000000-0000-4000-8000-0000000000de",
      version_number: 1,
      hook: "Hook",
      body: "Body text.",
      cta: null,
      hashtags: [],
      mentions: [],
      meta: {},
      source: "manual",
      change_note: null,
      created_by: null,
      created_at: now,
    },
    strategy: null,
    variants: [],
    limits: { max_length: 3000, hashtag_limit: 5 },
    editable: false,
    design_task: null,
    review: {
      request_id: "00000000-0000-4000-8000-0000000000df",
      status: "pending",
      round: 1,
      post_version: 1,
      creative_version: null,
      reviewer: null,
      reviewed_at: null,
      comments: [],
    },
    creatives: [],
  };
  await page.route(`**/api/v1/content/${id}`, (route) =>
    route.fulfill({ json: post }),
  );
  await page.goto(`/content/${id}`);

  await expect(
    page.getByRole("heading", { name: "Development company" }),
  ).toBeVisible();
  await expect(
    page.getByText("Waiting for content approval", { exact: true }),
  ).toHaveCount(1);
  await expect(
    page.getByText("Waiting for an admin to approve the copy"),
  ).toHaveCount(0);
  await expect(
    page.getByRole("link", { name: "Review & approve" }),
  ).toBeVisible();
});
