import { expect, type Page, test } from "@playwright/test";

/**
 * Blog as a content platform: the same Trend → Topic → Plan → Content →
 * Design → Approval journey as the social platforms, with an SEO plan,
 * long-form article editing, an article preview and Markdown export (never
 * auto-published). Uses live discovery, so it needs internet access; start
 * the API with TREND_SCHEDULER_ENABLED=false. Set E2E_OFFLINE=1 to skip.
 */

const PASSWORD = "correct-horse-battery"; // same test-only value as backend/tests/conftest.py
const SHOTS = process.env.E2E_SCREENSHOTS;

async function shot(page: Page, name: string) {
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true });
}

test.skip(!!process.env.E2E_OFFLINE, "needs internet access");

test("plan, write, design and approve a blog article", async ({ page }) => {
  test.setTimeout(180_000);

  await page.goto("/register");
  await page.getByLabel("Full name").fill("Bea Blogger");
  await page.getByLabel("Work email").fill(`e2e-blog-${Date.now()}@example.com`);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/onboarding/);
  await page.getByLabel("Organization name").fill("Longform Labs");
  await page.getByRole("button", { name: "Create organization" }).click();
  await expect(page).toHaveURL(/\/dashboard/);
  await page.getByRole("button", { name: "Skip tour" }).click();

  // Blog is offered alongside the social platforms; publish only there.
  await page.getByRole("link", { name: "Settings" }).first().click();
  await page.getByLabel("Target markets").fill("USA");
  await page.getByLabel("Target markets").press("Enter");
  await page.getByLabel("Keywords to track").fill("artificial intelligence");
  await page.getByLabel("Keywords to track").press("Enter");
  const platforms = page.getByRole("group", { name: "Platforms" });
  for (const name of ["LinkedIn", "X", "Instagram", "Facebook"]) {
    const chip = platforms.getByRole("button", { name, exact: true });
    if ((await chip.getAttribute("aria-pressed")) === "true") await chip.click();
  }
  const blogChip = platforms.getByRole("button", { name: "Blog", exact: true });
  if ((await blogChip.getAttribute("aria-pressed")) !== "true") await blogChip.click();
  await expect(blogChip).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText("Settings saved")).toBeVisible();

  // Discover, then shortlist the top trend.
  await page.getByRole("link", { name: "Trends", exact: true }).first().click();
  const startFirst = page.getByRole("button", { name: "Discover trends now" });
  const startAgain = page.getByRole("button", { name: "Discover now" });
  const inProgress = page.getByRole("button", { name: "Discovering…" });
  await expect(startFirst.or(startAgain).or(inProgress).first()).toBeVisible();
  if (await startFirst.isVisible()) await startFirst.click();
  else if (await startAgain.isEnabled()) await startAgain.click();
  const rows = page.getByRole("list", { name: "Trends" }).getByRole("listitem");
  await expect(rows.first()).toBeVisible({ timeout: 120_000 });
  await expect(page.getByRole("list", { name: "Trends" })).toHaveAttribute("aria-busy", "false");
  const topic = (await rows.first().getByRole("link").textContent())!.trim();
  await rows.first().getByRole("link").click();
  await expect(page.getByRole("heading", { level: 1, name: topic })).toBeVisible();
  const analyzeNow = page.getByRole("button", { name: "Analyze now" });
  if (await analyzeNow.isVisible()) await analyzeNow.click();
  await expect(page.getByText(/^Rule-based estimate/).first()).toBeVisible({ timeout: 30_000 });
  await page.getByRole("combobox", { name: /Relevance rating/ }).click();
  await page.getByRole("option", { name: "Highly relevant", exact: true }).click();
  await expect(page.getByText("Relevance updated")).toBeVisible();
  await page.getByRole("button", { name: `Shortlist ${topic}`, exact: true }).click();
  await expect(page.getByText(`Shortlisted “${topic}”`)).toBeVisible();

  // Topics can be filtered by Blog; open the shortlisted one.
  await page.getByRole("link", { name: "Topics", exact: true }).click();
  await page.getByRole("tab", { name: /^Shortlisted/ }).click();
  const topics = page.getByRole("list", { name: "Topics" });
  await expect(topics).toHaveAttribute("aria-busy", "false");
  await topics.getByRole("link", { name: topic, exact: true }).click();
  await expect(page.getByRole("heading", { level: 1, name: topic })).toBeVisible();

  // Blog plan: the playbook draft includes an SEO plan.
  await page.getByRole("button", { name: "New plan" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("combobox", { name: "Platform" }).click();
  await page.getByRole("option", { name: "Blog", exact: true }).click();
  const seoPlan = dialog.getByRole("group", { name: "SEO plan" });
  await expect(seoPlan).toBeVisible();
  await dialog.getByRole("button", { name: "Draft from playbook" }).click();
  await expect(dialog.getByLabel("Content angle")).not.toHaveValue("");
  await expect(seoPlan.getByLabel("Primary keyword")).not.toHaveValue("");
  await expect(seoPlan.getByLabel("Outline")).not.toHaveValue("");
  await seoPlan.getByLabel("Target words").fill("1800");
  await dialog.getByRole("button", { name: "Save plan" }).click();
  await expect(page.getByText("Blog plan saved")).toBeVisible();
  const strategy = page.getByRole("article").first();
  await expect(strategy.getByText("About 1,800 words")).toBeVisible();
  await expect(strategy.getByText("Outline", { exact: true })).toBeVisible();
  await shot(page, "blog-01-strategy");

  // Write the article from the saved plan (template engine: no AI model in E2E).
  await strategy.getByRole("button", { name: "Write article" }).click();
  await expect(page).toHaveURL(/\/content\//);
  await expect(page.getByText("Template draft", { exact: true })).toBeVisible({ timeout: 30_000 });
  const editor = page.getByRole("form", { name: "Post editor" });
  await expect(editor.getByText("Blog article", { exact: true })).toBeVisible();
  await expect(editor.getByLabel("Introduction")).not.toHaveValue("");
  await expect(editor.getByLabel("Body")).toHaveValue(/^## /);
  await expect(editor.getByLabel("Hashtags")).toHaveCount(0);
  const preview = page.getByRole("figure", { name: "Search result preview" });
  await expect(preview).toBeVisible();
  await expect(page.getByRole("heading", { level: 1 }).filter({ hasText: topic }).first()).toBeVisible();

  // SEO fields are versioned like the copy.
  await editor.getByLabel("Meta description").fill(`A practical guide to ${topic} for busy teams.`);
  await editor.getByLabel("Slug", { exact: true }).fill("practical-guide");
  await editor.getByRole("button", { name: "Save version" }).click();
  await expect(page.getByText("Saved as version 2")).toBeVisible();
  await expect(page.getByRole("list", { name: "Versions" }).getByText("Edited SEO details")).toBeVisible();
  await expect(preview).toContainText("practical-guide");
  await shot(page, "blog-02-studio");

  // Featured image: add it on the design task and submit, then one approval.
  await page.getByRole("button", { name: "Send to design" }).click();
  await expect(page).toHaveURL(/\/design\//);
  await expect(page.getByText("Design brief", { exact: true })).toBeVisible();
  await expect(page.getByText(/1200×630/).first()).toBeVisible();
  await expect(page.getByRole("figure", { name: "Search result preview" })).toBeVisible();
  await page.getByLabel("Choose creative files").setInputFiles("e2e/fixtures/creative-slide-1.png");
  await page.getByRole("button", { name: "Upload & submit for approval" }).click();
  await expect(page.getByText("Submitted for approval").first()).toBeVisible();

  await page.getByRole("link", { name: "Approvals", exact: true }).click();
  const queue = page.getByRole("list", { name: "Approvals" });
  await expect(queue.getByRole("link")).toHaveCount(1);
  await queue.getByRole("link").click();
  await expect(page.getByRole("figure", { name: "Search result preview" })).toContainText("practical-guide");
  await page.getByRole("button", { name: "Approve" }).click();
  await expect(page.getByText("Locked and ready to publish. Use Share on the post.")).toBeVisible();
  // Blog is exported for the website's CMS, never published automatically.
  await expect(page.getByRole("button", { name: "Copy article" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Download .md" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Share" })).toHaveCount(0);
  await shot(page, "blog-03-final");

  // The Blog playbook is editable like the others.
  await page.getByRole("link", { name: "Platform playbook" }).click();
  await page.getByRole("tab", { name: "Blog" }).click();
  await expect(page.getByRole("form", { name: "Blog playbook" })).toBeVisible();
  await expect(page.getByRole("form", { name: "Blog playbook" }).getByText("How-to guide")).toBeVisible();
});
