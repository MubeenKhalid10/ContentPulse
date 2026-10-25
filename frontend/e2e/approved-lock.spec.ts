import { expect, type Page, test } from "@playwright/test";

/**
 * Approved work is locked: the studio and the design page say so, the admin
 * gets a "Request changes" way back in, and buttons carry one action each.
 * Data is served by the test (rules: backend/tests/test_approved_lock.py).
 */

const PASSWORD = "correct-horse-battery"; // same test-only value as backend/tests/conftest.py
const now = new Date().toISOString();
const POST_ID = "00000000-0000-4000-8000-0000000000a1";
const TASK_ID = "00000000-0000-4000-8000-0000000000a2";
const REQUEST_ID = "00000000-0000-4000-8000-0000000000a3";

async function signUp(page: Page) {
  // The organization's creator is its admin.
  await page.goto("/register");
  await page.getByLabel("Full name").fill("Ari Admin");
  await page.getByLabel("Work email").fill(`e2e-lock-${Date.now()}@example.com`);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/onboarding/);
  await page.getByLabel("Organization name").fill("Lock Co");
  await page.getByRole("button", { name: "Create organization" }).click();
  await expect(page).toHaveURL(/\/dashboard/);
  await page.getByRole("button", { name: "Skip tour" }).click();
}

const review = (status: string, creative: number | null) => ({
  request_id: REQUEST_ID,
  status,
  round: 1,
  post_version: 1,
  creative_version: creative,
  reviewer: null,
  reviewed_at: now,
  comments: [],
});

function post(status: string, reviewed: ReturnType<typeof review>) {
  return {
    id: POST_ID,
    title: "Launch post",
    platform: "linkedin",
    status,
    current_version: 1,
    hook: "Hook",
    topic: null,
    content_strategy_id: null,
    variant_of_id: null,
    generation: null,
    created_at: now,
    updated_at: now,
    current: {
      id: "00000000-0000-4000-8000-0000000000a4",
      version_number: 1,
      hook: "Hook",
      body: "Approved body text.",
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
    design_task: { id: TASK_ID, status: "open" },
    review: reviewed,
    creatives: [],
  };
}

test("approved copy is locked and the design button says one thing", async ({ page }) => {
  await signUp(page);
  await page.route(`**/api/v1/content/${POST_ID}`, (route) =>
    route.fulfill({ json: post("design_pending", review("approved", null)) }),
  );
  await page.goto(`/content/${POST_ID}`);

  await expect(page.getByText("Approved copy is locked")).toBeVisible();
  await expect(page.getByRole("link", { name: "Add design", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: /&/ })).toHaveCount(0);
  await expect(page.getByLabel("Body", { exact: false }).first()).toBeDisabled();
  // The admin's way back in: the approval, where changes can be requested.
  await expect(page.getByRole("link", { name: "Request changes" })).toHaveAttribute(
    "href",
    new RegExp(`/approvals/${REQUEST_ID}`),
  );
});

test("an approved design is locked on its design page", async ({ page }) => {
  await signUp(page);
  await page.route(`**/api/v1/design/tasks/${TASK_ID}`, (route) =>
    route.fulfill({
      json: {
        id: TASK_ID,
        status: "completed",
        format: "single_image",
        dimensions: "1200x630",
        headline: "Launch",
        post: {
          id: POST_ID,
          title: "Launch post",
          platform: "linkedin",
          status: "final",
          current_version: 1,
          topic_title: null,
        },
        assignee: null,
        creative_versions: 1,
        source: "rules",
        created_at: now,
        updated_at: now,
        submitted_at: now,
        visual_concept: null,
        supporting_text: null,
        slide_structure: [],
        visual_elements: [],
        brand_requirements: {},
        cta: null,
        designer_notes: null,
        content: { version: 1, hook: "Hook", body: "Body.", cta: null, hashtags: [] },
        brand: {
          brand_voice: null,
          tone: null,
          colors: [],
          typography: null,
          content_guidelines: null,
          forbidden_terms: [],
          logo_url: null,
          logo_position: "top_left",
        },
        creatives: [],
        storage: "local",
        max_upload_mb: 25,
        allowed_types: ["image/png"],
        ai_brief_pending: false,
        ai_images: false,
        image_job: null,
        review: review("approved", 1),
      },
    }),
  );
  await page.goto(`/design/${TASK_ID}`);

  await expect(page.getByText("Approved design is locked")).toBeVisible();
  await expect(page.getByRole("button", { name: "Submit for approval" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Request changes" })).toBeVisible();
});
