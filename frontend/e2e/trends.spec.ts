import { readFileSync } from "node:fs";
import { expect, type Locator, type Page, test } from "@playwright/test";

/**
 * Sprints 3-8, against the real free sources (Google Trends, Google News,
 * Hacker News, Reddit RSS): discover, analyze, shortlist, then plan content
 * for the resulting topic, write the post, deliver its design and approve it. Needs internet access. Start the API with
 * TREND_SCHEDULER_ENABLED=false so a scheduled run doesn't race this test.
 * Set E2E_OFFLINE=1 to skip.
 */

const PASSWORD = "correct-horse-battery"; // same test-only value as backend/tests/conftest.py
const SHOTS = process.env.E2E_SCREENSHOTS;

async function shot(page: Page, name: string) {
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true });
}

test.skip(!!process.env.E2E_OFFLINE, "needs internet access");

test("discover live trends, shortlist one and plan content for it", async ({ page }) => {
  test.setTimeout(180_000);

  await page.goto("/register");
  await page.getByLabel("Full name").fill("Tia Trends");
  await page.getByLabel("Work email").fill(`e2e-trends-${Date.now()}@example.com`);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/onboarding/);
  await page.getByLabel("Organization name").fill("Signal & Co");
  await page.getByRole("button", { name: "Create organization" }).click();
  await expect(page).toHaveURL(/\/dashboard/);
  await page.getByRole("button", { name: "Skip tour" }).click();

  // Markets + keywords drive what sources search for.
  await page.getByRole("link", { name: "Content setup" }).click();
  await page.getByLabel("Target markets").fill("USA");
  await page.getByLabel("Target markets").press("Enter");
  await page.getByLabel("Keywords to track").fill("artificial intelligence");
  await page.getByLabel("Keywords to track").press("Enter");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText("Content setup saved")).toBeVisible();

  // Sources: one click from Trends; free ones ready, keyed ones explain what's missing.
  await page.getByRole("link", { name: "Trends", exact: true }).click();
  const strip = page.getByRole("region", { name: "Trend sources" });
  await expect(strip).toContainText(/Watching \d+ sources/);
  await strip.getByRole("link", { name: "Manage sources" }).click();
  await expect(page).toHaveURL(/\/trends\/sources$/);
  // A source's own settings sit on its card: subreddits under Reddit.
  const subreddits = page.getByLabel("Subreddits to follow");
  await subreddits.fill("r/automation");
  await subreddits.press("Enter");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText("Subreddits saved")).toBeVisible();
  const ready = page.getByRole("region", { name: "Ready to use" });
  await expect(ready.getByRole("heading", { name: "Google Trends" })).toBeVisible();
  await expect(ready.getByRole("heading", { name: "Hacker News" })).toBeVisible();
  const setup = page.getByRole("region", { name: "Needs setup" });
  await expect(setup.getByText("X_BEARER_TOKEN", { exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "Not available" }).getByRole("heading", { name: "LinkedIn" })).toBeVisible();
  await shot(page, "trends-01-sources");

  // Discover against the live internet.
  await page.getByRole("link", { name: "Trends", exact: true }).first().click();
  // New organizations get a scheduled first run within a minute, so discovery
  // may already be under way; otherwise start it.
  const startFirst = page.getByRole("button", { name: "Discover New Trends now" }).first();
  const startAgain = page.getByRole("button", { name: "Discover New Trends now" }).last();
  const inProgress = page.getByRole("button", { name: "Discovering…" });
  await expect(startFirst.or(startAgain).or(inProgress).first()).toBeVisible();
  if (await startFirst.isVisible()) await startFirst.click();
  else if (await startAgain.isEnabled()) await startAgain.click();
  const rows = page.getByRole("list", { name: "Trends" }).getByRole("listitem");
  await expect(rows.first()).toBeVisible({ timeout: 120_000 });
  await expect(page.getByRole("list", { name: "Trends" })).toHaveAttribute("aria-busy", "false");
  // Per-source results are shown; at least one free source succeeded.
  await expect(page.getByRole("list", { name: "Source results" })).toContainText("Google Trends");
  await shot(page, "trends-02-list");

  // Open the top trend: explained score and linked evidence.
  const topic = (await rows.first().getByRole("link").textContent())!.trim();
  // The discovery schedule can be changed right here.
  await page.getByRole("combobox", { name: "How often to check for new trends" }).click();
  await page.getByRole("option", { name: "Once a day", exact: true }).click();
  await expect(page.getByText("Discovery schedule saved")).toBeVisible();
  await rows.first().getByRole("link").click();
  await expect(page.getByRole("heading", { level: 1, name: topic })).toBeVisible();
  await expect(page.getByText("Why it's trending", { exact: true })).toBeVisible();
  // Relevance analysis (Sprint 4). Without an AI model configured, discovery
  // runs the rule-based estimate automatically; trigger it if it hasn't yet.
  await expect(page.getByText("Relevance to your organization", { exact: true })).toBeVisible();
  const analyzeNow = page.getByRole("button", { name: "Analyze now" });
  if (await analyzeNow.isVisible()) await analyzeNow.click();
  await expect(page.getByText(/^Rule-based estimate/).first()).toBeVisible({ timeout: 30_000 });
  await page.getByRole("combobox", { name: /Relevance rating/ }).click();
  await page.getByRole("option", { name: "Highly relevant", exact: true }).click();
  await expect(page.getByText("Relevance updated")).toBeVisible();
  await expect(page.getByText("· set manually").first()).toBeVisible();
  // Evidence starts folded; opening it lists the mentions by source.
  const evidence = page.getByRole("button", { name: /^Evidence \(\d+\)/ });
  await expect(evidence).toHaveAttribute("aria-expanded", "false");
  await evidence.click();
  await expect(evidence).toHaveAttribute("aria-expanded", "true");
  const evidencePanel = page.locator(`[id="${await evidence.getAttribute("aria-controls")}"]`);
  await expect(evidencePanel.getByRole("link").first()).toBeVisible();
  await shot(page, "trends-03-detail");

  await page.getByRole("button", { name: `Shortlist ${topic}`, exact: true }).click();
  await expect(page.getByText(`Shortlisted “${topic}”`)).toBeVisible();
  await page.getByRole("link", { name: "Trends", exact: true }).first().click();
  await page.getByRole("tab", { name: "Shortlisted" }).click();
  const shortlisted = page.getByRole("list", { name: "Trends" });
  await expect(shortlisted).toHaveAttribute("aria-busy", "false");
  await expect(shortlisted.getByRole("link", { name: topic, exact: true })).toBeVisible();
  await expect(shortlisted.getByRole("listitem")).toHaveCount(1);

  // Sprint 5: shortlisting the trend shortlisted its topic candidate.
  await page.getByRole("link", { name: "Topics", exact: true }).click();
  await page.getByRole("tab", { name: /^Shortlisted/ }).click();
  const topics = page.getByRole("list", { name: "Topics" });
  await expect(topics).toHaveAttribute("aria-busy", "false");
  await expect(topics.getByRole("link")).toHaveCount(1);
  await topics.getByRole("link", { name: topic, exact: true }).click();
  await expect(page.getByRole("heading", { level: 1, name: topic })).toBeVisible();
  await expect(page.getByText("Recommended platforms", { exact: true })).toBeVisible();
  await expect(page.getByText("Relevance to your organization", { exact: true })).toBeVisible();

  // Plan a post and write it in one step: draft the plan from the playbook (no
  // AI model in E2E), then "Save & write post" opens the studio.
  await page.getByRole("button", { name: "New plan" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "Draft from playbook" }).click();
  await expect(dialog.getByLabel("Content angle")).not.toHaveValue("");
  await shot(page, "topics-01-detail");
  await dialog.getByRole("button", { name: "Save & write post" }).click();
  await expect(page).toHaveURL(/\/content\//);
  await expect(page.getByText("Template draft", { exact: true })).toBeVisible({ timeout: 30_000 });

  // Edit the copy as a new version, then send it to design.
  const editor = page.getByRole("form", { name: "Post editor" });
  await editor.getByLabel("Hook").fill("A sharper opening line written by a person.");
  await editor.getByRole("button", { name: "Save version" }).click();
  await expect(page.getByText("Saved as version 2")).toBeVisible();
  const history = page.getByRole("list", { name: "Versions" });
  await expect(history.getByRole("listitem")).toHaveCount(2);
  await expect(history.getByText("Edited hook")).toBeVisible();
  // The plan behind the post folds away and opens on demand.
  const plan = page.getByRole("button", { name: /^Plan For / });
  await expect(plan).toHaveAttribute("aria-expanded", "false");
  // The page re-renders once the new version lands: retry until it stays open.
  await expect(async () => {
    if ((await plan.getAttribute("aria-expanded")) !== "true") await plan.click();
    await expect(page.getByRole("link", { name: "Open the topic" })).toBeVisible({ timeout: 1_000 });
  }).toPass();
  await shot(page, "content-01-studio");
  const studioUrl = page.url();
  await page.getByRole("button", { name: "Send to design" }).click();

  // "Send to design" lands on the design task: brief, copy and brand rules,
  // then the creative goes up through a signed URL.
  await expect(page).toHaveURL(/\/design\//);
  await expect(page.getByText("Design brief", { exact: true })).toBeVisible();
  await expect(page.getByText("Brand guidelines", { exact: true })).toBeVisible();
  // A long file name must not push the card out of its column.
  const longName = `Gemini_Generated_Image_${"j3kd95j3kd95".repeat(6)}.png`;
  await page.getByLabel("Choose creative files").setInputFiles({
    name: longName,
    mimeType: "image/png",
    buffer: readFileSync("e2e/fixtures/creative-slide-1.png"),
  });
  const card = page.getByRole("button", { name: "Upload & submit for approval" });
  const cardBox = await page.getByText("Add the design", { exact: true }).locator("xpath=ancestor::*[@data-slot='card'][1]").boundingBox();
  const buttonBox = await card.boundingBox();
  expect(buttonBox!.x + buttonBox!.width).toBeLessThanOrEqual(cardBox!.x + cardBox!.width);
  await shot(page, "design-00-selected");
  await page.getByLabel("Note for this version").fill("First pass");
  await page.getByRole("button", { name: "Upload only (don't submit yet)" }).click();
  await expect(page.getByText("Saved as version 1")).toBeVisible();
  const version = page.getByRole("region", { name: "Version 1" });
  await expect(version.getByRole("img", { name: longName })).toBeVisible();
  await expect(version.getByText("First pass")).toBeVisible();

  // Colours can be adjusted for this post without touching Brand settings.
  await page.getByRole("button", { name: "Adjust colors" }).click();
  await page.getByRole("button", { name: "Add color" }).click();
  const colorInputs = page.getByRole("textbox", { name: /^Color \d+$/ });
  await colorInputs.last().fill("#FF5500");
  await page.getByRole("button", { name: "Save colors" }).click();
  await expect(page.getByText("Colors saved for this post")).toBeVisible();
  const palette = page.getByRole("list", { name: "Colors for this post" });
  await expect(palette.getByText("#FF5500")).toBeVisible();
  await expect(page.getByText("Adjusted for this post")).toBeVisible();
  await shot(page, "design-01-task");
  await page.getByRole("button", { name: "Use brand colors" }).click();
  await expect(page.getByText("Back to your brand colors")).toBeVisible();

  // The real logo (Profile > Logo URL) can be moved for this post.
  await expect(page.getByText(/No logo yet/)).toBeVisible();
  const me = await (await page.request.get("/api/v1/auth/me")).json();
  const profile = await page.request.patch(`/api/v1/organizations/${me.organization_id}`, {
    data: { logo_url: "http://127.0.0.1:8088/big-logo.png" }, // 1200×1200: must stay in its box
  });
  expect(profile.ok()).toBeTruthy();
  await page.reload();
  // The preview is a white frame shaped like the image, logo at its real spot.
  const logoPreview = page.getByRole("img", { name: "Your logo, bottom right" });
  await expect(logoPreview).toBeVisible();
  // Compact thumbnail: logo drawn larger (up to 40%) so it stays recognisable.
  await expectLogoAt(logoPreview, "bottom", "right", { maxWidth: 0.4, maxHeight: 0.4 });
  expect((await logoPreview.boundingBox())!.width).toBeLessThanOrEqual(120);
  await shot(page, "design-02a-logo-preview");
  await page.getByRole("button", { name: "Change position" }).click();
  const picker = page.getByRole("group", { name: "Logo position for this post" });
  const pickerFrame = picker.locator("div.relative").first();
  await expectLogoAt(pickerFrame, "bottom", "right");
  await picker.getByRole("radio", { name: "Bottom centre" }).check({ force: true });
  await expectLogoAt(pickerFrame, "bottom", "center");
  await shot(page, "design-02-logo");
  await page.getByRole("button", { name: "Save position" }).click();
  await expect(page.getByText("Logo position saved for this post")).toBeVisible();
  await expect(page.getByText("Moved for this post")).toBeVisible();
  await page.getByRole("button", { name: "Use brand position" }).click();
  await expect(page.getByText("Logo back to the brand position")).toBeVisible();
  await page.getByRole("button", { name: "Submit current design for approval" }).click();
  await expect(page.getByText("Submitted for approval").first()).toBeVisible();
  await expect(page.getByText("Waiting for approval", { exact: true }).first()).toBeVisible();
  await page.getByRole("link", { name: "Design", exact: true }).first().click();
  await page.getByRole("tab", { name: /^Waiting for approval/ }).click();
  await expect(page.getByRole("list", { name: "Design tasks" }).getByRole("link")).toHaveCount(1);
  await page.getByRole("link", { name: "Content studio", exact: true }).first().click();
  await page.getByRole("tab", { name: /^Waiting for approval/ }).click();
  await expect(page.getByRole("list", { name: "Posts" }).getByRole("link")).toHaveCount(1);

  // Review: ask for changes, the creator uploads a new design and resubmits
  // in one click, then one "Approve" makes the post ready to publish.
  await page.getByRole("link", { name: "Approvals", exact: true }).click();
  const queue = page.getByRole("list", { name: "Approvals" });
  await expect(queue.getByRole("link")).toHaveCount(1);
  await queue.getByRole("link").click();
  // Copy and design in one frame, as the platform shows them.
  const preview = page.getByRole("article", { name: /post preview$/ });
  await expect(preview.getByRole("img", { name: longName })).toBeVisible();
  await expect(preview).toContainText("A sharper opening line written by a person.");
  await expect(page.getByText("Original topic", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Request changes" }).click();
  const changes = page.getByRole("alertdialog");
  await changes.getByLabel("What should change").fill("Use a stronger headline on the image.");
  await changes.getByRole("button", { name: "Request changes" }).click();
  await expect(page.getByRole("list", { name: "Comments" })).toContainText("Use a stronger headline on the image.");
  await shot(page, "approvals-01-review");
  // The creator goes back to the post in Content studio.
  await page.goto(studioUrl);
  await expect(page.getByText(/^Changes requested \(round 1\)/)).toBeVisible();
  await page.getByRole("link", { name: "Update design & resubmit" }).click();
  await expect(page.getByText("Use a stronger headline on the image.")).toBeVisible();
  await page.getByLabel("Choose creative files").setInputFiles("e2e/fixtures/creative-slide-1.png");
  await page.getByRole("button", { name: "Upload & submit for approval" }).click();
  await expect(page.getByText("Submitted for approval").first()).toBeVisible();
  await page.getByRole("link", { name: "Approvals", exact: true }).click();
  await expect(queue.getByText("Round 2")).toBeVisible();
  await queue.getByRole("link").click();
  await page.getByRole("button", { name: "Approve" }).click();
  await expect(page.getByText("Locked and ready to publish. Use Share on the post.")).toBeVisible();
  await shot(page, "approvals-02-final");

  // Platform rules live in the database and are editable (spec §22).
  await page.getByRole("link", { name: "Platform playbook" }).click();
  await expect(page.getByRole("form", { name: "LinkedIn playbook" })).toBeVisible();
  await page.getByLabel("Tone").fill("Bold and practical");
  await page.getByRole("button", { name: "Save playbook" }).click();
  await expect(page.getByText("LinkedIn playbook saved")).toBeVisible();

  // Dashboard: the pipeline counts the shortlisted topic and the approved post;
  // the period's numbers include what this run discovered and wrote.
  await page.getByRole("link", { name: "Dashboard" }).click();
  const flow = page.getByRole("region", { name: "Content pipeline" });
  await expect(flow.getByRole("link", { name: /Shortlisted$/ })).toContainText("1");
  await expect(flow.getByRole("link", { name: /Ready to publish$/ })).toContainText("1");
  const numbers = page.getByRole("region", { name: "Key numbers" });
  await expect(numbers.getByRole("link", { name: /^Posts written/ })).toContainText(/[1-9]/);
  await expect(numbers.getByRole("link", { name: /^Approved to publish/ })).toContainText(/[1-9]/);
  await expect(page.getByRole("table")).toBeVisible(); // trending topics
  await expect(page.getByRole("list", { name: "Recent content" }).getByRole("listitem").first()).toBeVisible();
  await shot(page, "trends-04-dashboard");
});

/** The (1200×1200) logo sits inside its frame where the server will place it:
 * at most 18% wide and 12% tall, 4% from the chosen edges. */
async function expectLogoAt(
  frame: Locator,
  vertical: "top" | "bottom",
  horizontal: "left" | "center" | "right",
  { maxWidth = 0.18, maxHeight = 0.12 } = {},
) {
  const box = (await frame.boundingBox())!;
  const logo = (await frame.locator("img").boundingBox())!;
  const near = (a: number, b: number) => expect(Math.abs(a - b)).toBeLessThanOrEqual(2);
  // The server's margin: 4% of the image's short side, on every edge. The frame
  // has a 1px border, so measure from its inner box.
  const inner = { x: box.x + 1, y: box.y + 1, width: box.width - 2, height: box.height - 2 };
  const margin = Math.min(inner.width, inner.height) * 0.04;
  expect(logo.width).toBeLessThanOrEqual(inner.width * maxWidth + 1);
  expect(logo.height).toBeLessThanOrEqual(inner.height * maxHeight + 1);
  if (vertical === "bottom") near(logo.y + logo.height, inner.y + inner.height - margin);
  else near(logo.y, inner.y + margin);
  if (horizontal === "right") near(logo.x + logo.width, inner.x + inner.width - margin);
  else if (horizontal === "left") near(logo.x, inner.x + margin);
  else near(logo.x + logo.width / 2, inner.x + inner.width / 2);
}
