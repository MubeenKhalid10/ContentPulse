import { expect, type Page, test } from "@playwright/test";

/**
 * Design task page: the post copy comes first, then everything about the
 * design under one "Design" heading; an older creative version can be made
 * the newest. Task data is served by the test (backend behavior is covered by
 * backend/tests/test_design_versions.py).
 */

const PASSWORD = "correct-horse-battery"; // same test-only value as backend/tests/conftest.py
const ID = "00000000-0000-4000-8000-0000000000e1";
const now = new Date().toISOString();
const PNG =
  "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=";

async function signUp(page: Page) {
  await page.goto("/register");
  await page.getByLabel("Full name").fill("Dani Design");
  await page.getByLabel("Work email").fill(`e2e-design-${Date.now()}@example.com`);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/onboarding/);
  await page.getByLabel("Organization name").fill("Design Co");
  await page.getByRole("button", { name: "Create organization" }).click();
  await expect(page).toHaveURL(/\/dashboard/);
  await page.getByRole("button", { name: "Skip tour" }).click();
}

const version = (n: number, name: string, note: string | null) => ({
  version: n,
  note,
  uploaded_by: { id: "u1", name: "Dani Design", email: "dani@example.com" },
  created_at: now,
  files: [
    {
      id: `00000000-0000-4000-8000-00000000f00${n}`,
      file_name: name,
      file_type: "image/png",
      file_size: 68,
      position: 0,
      url: PNG,
      download_url: PNG,
    },
  ],
});

function task(creatives: ReturnType<typeof version>[]) {
  return {
    id: ID,
    status: "in_progress",
    format: "single_image",
    dimensions: "1200x630",
    headline: "Choosing a partner",
    post: {
      id: "00000000-0000-4000-8000-0000000000e2",
      title: "Development company",
      platform: "linkedin",
      status: "design_uploaded",
      current_version: 1,
      topic_title: "Development company",
    },
    assignee: null,
    creative_versions: creatives.length,
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
    creatives,
    storage: "local",
    max_upload_mb: 25,
    allowed_types: ["image/png"],
    ai_brief_pending: false,
    ai_images: false,
    image_job: null,
    review: null,
  };
}

test("copy first, design grouped, and an older version can be used again", async ({ page }) => {
  await signUp(page);
  const before = [version(2, "second.png", null), version(1, "first.png", null)];
  const after = [version(3, "first.png", "Reused version 1"), ...before];
  const used: string[] = [];
  // After "Use", the page reloads the task: serve the new version list then.
  await page.route(`**/api/v1/design/tasks/${ID}`, (route) =>
    route.fulfill({ json: task(used.length ? after : before) }),
  );
  await page.route(`**/api/v1/design/tasks/${ID}/versions/*/use`, (route) => {
    used.push(new URL(route.request().url()).pathname);
    return route.fulfill({ json: task(after) });
  });
  await page.goto(`/design/${ID}`);

  // Post copy sits above the Design group, which holds the brief, brand and files.
  const copy = page.getByText("Post Content", { exact: true });
  const design = page.getByRole("region", { name: "Design" });
  await expect(copy).toBeVisible();
  await expect(design).toBeVisible();
  expect((await copy.boundingBox())!.y).toBeLessThan((await design.boundingBox())!.y);
  await expect(design.getByText("Design brief", { exact: true })).toBeVisible();
  await expect(design.getByText("Brand guidelines", { exact: true })).toBeVisible();
  await expect(design.getByText("Creative versions", { exact: true })).toBeVisible();

  // The newest version has no button; older ones do.
  await expect(page.getByRole("button", { name: "Use version 2" })).toHaveCount(0);
  await page.getByRole("button", { name: "Use version 1" }).click();
  await expect(page.getByText("Version 1 is now the newest")).toBeVisible();
  expect(used).toEqual([`/api/v1/design/tasks/${ID}/versions/1/use`]);
  await expect(page.getByRole("region", { name: "Version 3" })).toContainText("Reused version 1");
});
