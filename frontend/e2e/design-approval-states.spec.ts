import { expect, type Page, test } from "@playwright/test";

/**
 * Nothing can be submitted or changed while the work behind it is still running,
 * and the Ready to publish tab shows its count. Data is served by the test.
 */

const PASSWORD = "correct-horse-battery"; // same test-only value as backend/tests/conftest.py
const TASK = "00000000-0000-4000-8000-0000000000f1";
const POST = "00000000-0000-4000-8000-0000000000f2";
const APPROVAL = "00000000-0000-4000-8000-0000000000f3";
const now = new Date().toISOString();
const PNG =
  "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=";

async function signUp(page: Page) {
  await page.goto("/register");
  await page.getByLabel("Full name").fill("Sam States");
  await page.getByLabel("Work email").fill(`e2e-states-${Date.now()}@example.com`);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/onboarding/);
  await page.getByLabel("Organization name").fill("States Co");
  await page.getByRole("button", { name: "Create organization" }).click();
  await expect(page).toHaveURL(/\/dashboard/);
  await page.getByRole("button", { name: "Skip tour" }).click();
}

const creative = {
  version: 1,
  note: null,
  uploaded_by: { id: "u1", name: "Sam States", email: "sam@example.com" },
  created_at: now,
  files: [
    {
      id: "00000000-0000-4000-8000-0000000000f4",
      file_name: "first.png",
      file_type: "image/png",
      file_size: 68,
      position: 0,
      url: PNG,
      download_url: PNG,
    },
  ],
};

const task = (imageStatus: string) => ({
  id: TASK,
  status: "in_progress",
  format: "single_image",
  dimensions: "1200x630",
  headline: "Choosing a partner",
  post: { id: POST, title: "A post", platform: "linkedin", status: "design_uploaded", current_version: 1, topic_title: "A topic" },
  assignee: null,
  creative_versions: 1,
  source: "rules",
  created_at: now,
  updated_at: now,
  submitted_at: null,
  visual_concept: "Two people reviewing wireframes.",
  supporting_text: null,
  slide_structure: [],
  visual_elements: [],
  brand_requirements: {},
  cta: null,
  designer_notes: null,
  content: { version: 1, hook: "The copy hook", body: "The copy body.", cta: null, hashtags: [] },
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
  creatives: [creative],
  storage: "s3",
  max_upload_mb: 25,
  allowed_types: ["image/png"],
  ai_brief_pending: false,
  ai_images: true,
  image_job: { status: imageStatus, error: null, version: imageStatus === "succeeded" ? 1 : null },
  review: null,
});

const approval = {
  id: APPROVAL,
  stage: "design",
  status: "pending",
  round: 1,
  post: { id: POST, title: "A post", platform: "linkedin", status: "pending_approval", current_version: 1 },
  topic_title: null,
  post_version: 1,
  creative_version: 1,
  preview_url: null,
  submitted_by: null,
  reviewer: null,
  comment_count: 0,
  created_at: now,
  reviewed_at: null,
};

test("a design can't be submitted until its AI image is ready", async ({ page }) => {
  await signUp(page);
  let status = "running";
  await page.route(`**/api/v1/design/tasks/${TASK}`, (route) => route.fulfill({ json: task(status) }));
  await page.goto(`/design/${TASK}`);

  const submit = page.getByRole("button", { name: "Submit for approval" });
  await expect(page.getByRole("button", { name: "Creating image…" })).toBeDisabled();
  await expect(submit).toBeDisabled();
  await expect(page.getByText("You can submit once the AI image is ready.")).toBeVisible();

  status = "succeeded";
  await expect(submit).toBeEnabled();
  await expect(page.getByText("AI image ready", { exact: true })).toBeVisible();
  await expect(page.getByText("You can submit once the AI image is ready.")).toHaveCount(0);
});

test("a failed AI image says so and frees the button", async ({ page }) => {
  await signUp(page);
  let status = "running";
  await page.route(`**/api/v1/design/tasks/${TASK}`, (route) => route.fulfill({ json: task(status) }));
  await page.goto(`/design/${TASK}`);
  await expect(page.getByRole("button", { name: "Submit for approval" })).toBeDisabled();

  status = "failed";
  await expect(page.getByText("The AI image couldn't be created")).toBeVisible();
  await expect(page.getByRole("button", { name: "Submit for approval" })).toBeEnabled();
});

test("the change options lock while the request is being sent", async ({ page }) => {
  await signUp(page);
  let release = () => {};
  const held = new Promise<void>((resolve) => (release = resolve));
  const detail = {
    ...approval,
    content: null,
    copy_changed_since: false,
    creative,
    creatives: [creative],
    versions: [],
    brief: null,
    topic: null,
    comments: [],
    history: [],
  };
  await page.route(`**/api/v1/approvals/${APPROVAL}`, (route) => route.fulfill({ json: detail }));
  await page.route(`**/api/v1/approvals/${APPROVAL}/request-changes`, async (route) => {
    await held;
    await route.fulfill({ json: detail });
  });
  await page.goto(`/approvals/${APPROVAL}`);
  await page.getByRole("button", { name: /Request changes/ }).first().click();

  const dialog = page.getByRole("alertdialog");
  await dialog.getByRole("radio", { name: /^Content/ }).click();
  await dialog.getByLabel("What should change").fill("Shorten the headline");
  await dialog.getByRole("button", { name: "Request changes" }).click();

  await expect(dialog.getByRole("button", { name: "Sending…" })).toBeDisabled();
  for (const name of [/^Content/, /^Design/, /^Both/]) {
    await expect(dialog.getByRole("radio", { name })).toBeDisabled();
  }
  await expect(dialog.getByLabel("What should change")).toBeDisabled();
  await expect(dialog.getByRole("radio", { name: /^Content/ })).toBeChecked();

  release();
  await expect(page.getByText("Changes requested")).toBeVisible();
});

test("Ready to publish shows its count on every tab", async ({ page }) => {
  await signUp(page);
  await page.route(/\/api\/v1\/approvals\?/, (route) =>
    route.fulfill({
      json: {
        items: [approval],
        total: 1,
        counts: { pending: 1, reviewed: 3, approved: 3, changes_requested: 0, rejected: 0, all: 4 },
        stage_pending: { copy: 2, design: 1 },
        ready_count: 3,
      },
    }),
  );
  await page.goto("/approvals");
  const ready = page.getByRole("tab", { name: /Ready to publish/ });
  await expect(ready).toHaveText("Ready to publish3");
  await ready.click();
  await expect(ready).toHaveText("Ready to publish3");
  await expect(page.getByRole("tab", { name: /Content approval/ })).toHaveText("Content approval2");
});

test("every file of a version is shown whole, one at a time", async ({ page }) => {
  await signUp(page);
  const wide = (fill: string) =>
    `data:image/svg+xml,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="2400" height="900"><rect width="2400" height="900" fill="${fill}"/></svg>`)}`;
  const files = ["red", "green", "blue"].map((fill, i) => ({
    ...creative.files[0],
    id: `00000000-0000-4000-8000-00000000a00${i}`,
    file_name: `${fill}.png`,
    url: wide(fill),
    download_url: wide(fill),
  }));
  await page.route(`**/api/v1/design/tasks/${TASK}`, (route) =>
    route.fulfill({ json: { ...task("succeeded"), creatives: [{ ...creative, files }] } }),
  );
  await page.goto(`/design/${TASK}`);

  const version = page.getByRole("region", { name: "Version 1" });
  const carousel = version.getByRole("group", { name: /Version 1 files/ });
  const box = (await version.boundingBox())!;
  const seen = async (name: string) => {
    const image = version.getByRole("img", { name });
    await expect(async () => {
      const b = (await image.boundingBox())!;
      // Nothing wider than the card, and nothing cut off by its edge.
      expect(b.x).toBeGreaterThanOrEqual(box.x - 1);
      expect(b.x + b.width).toBeLessThanOrEqual(box.x + box.width + 1);
    }).toPass();
  };
  await expect(carousel).toBeVisible();
  await seen("red.png");
  await expect(version.getByText("1 of 3")).toBeVisible();
  await expect(version.getByRole("button", { name: "Previous file" })).toBeDisabled();

  await version.getByRole("button", { name: "Next file" }).click();
  await expect(version.getByText("2 of 3")).toBeVisible();
  await seen("green.png");

  await version.getByRole("button", { name: /Show file 3/ }).click();
  await expect(version.getByText("3 of 3")).toBeVisible();
  await seen("blue.png");
  await expect(version.getByRole("button", { name: "Next file" })).toBeDisabled();

  await carousel.focus();
  await page.keyboard.press("ArrowLeft");
  await expect(version.getByText("2 of 3")).toBeVisible();

  // Each file keeps its own download link.
  await expect(version.getByRole("link", { name: "Download blue.png" })).toHaveCount(1);
  await expect(page.locator("main").evaluate((m) => m.scrollWidth <= m.clientWidth)).resolves.toBe(true);
});
