import { expect, type Page, test } from "@playwright/test";

/**
 * Sprint 2: an admin crawls the organization's website, the knowledge base
 * fills up, retrieval finds the right passages, and documents can be
 * inspected, excluded and added manually.
 *
 * Requires the API to run with CRAWLER_ALLOW_PRIVATE_NETWORKS=true so it may
 * crawl the fixture site on 127.0.0.1:8088 (started by playwright.config.ts).
 */

const PASSWORD = "correct-horse-battery"; // same test-only value as backend/tests/conftest.py
const SITE = "http://127.0.0.1:8088";
const SHOTS = process.env.E2E_SCREENSHOTS;

async function shot(page: Page, name: string) {
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true });
}

test("admin builds and searches the knowledge base", async ({ page }) => {
  // Sign up and create an organization whose website is the fixture site.
  await page.goto("/register");
  await page.getByLabel("Full name").fill("Kai Knowledge");
  await page.getByLabel("Work email").fill(`e2e-kb-${Date.now()}@example.com`);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/onboarding/);
  await page.getByLabel("Organization name").fill("Northwind Labs");
  await page.getByLabel("Website").fill(SITE);
  await page.getByRole("button", { name: "Create organization" }).click();
  await expect(page).toHaveURL(/\/dashboard/);
  await page.getByRole("button", { name: "Skip tour" }).click();
  await expect(page.getByText("Add your website to the knowledge base")).toBeVisible();

  // Empty state → crawl.
  await page.getByRole("link", { name: "Knowledge base", exact: true }).click();
  await expect(page.getByText("Teach ContentPulse about your business")).toBeVisible();
  await shot(page, "kb-01-empty");
  await page.getByRole("button", { name: "Crawl website" }).click();
  await expect(page.getByRole("textbox", { name: "Website" })).toHaveValue(`${SITE}/`);
  await page.getByRole("button", { name: "Start crawl" }).click();

  // Background job completes; the page refreshes itself.
  await expect(page.getByText(/Crawl finished: 3 pages indexed/)).toBeVisible({ timeout: 45_000 });
  await expect(page.getByRole("button", { name: "Services | Northwind Labs", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "About | Northwind Labs", exact: true })).toBeVisible();
  // robots.txt disallows /private, and the cookie banner/footers are stripped.
  await expect(page.getByText("salary bands")).toHaveCount(0);
  await shot(page, "kb-02-crawled");

  // Retrieval: the question finds the AI agents section.
  await page.getByLabel("Search the knowledge base").fill("reconcile invoices automatically");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  const firstHit = page.getByRole("search").locator("..").getByRole("listitem").first();
  await expect(firstHit).toContainText("Services | Northwind Labs");
  await expect(firstHit).toContainText("reconcile invoices");
  await expect(firstHit.locator("mark").first()).toBeVisible();
  await shot(page, "kb-03-search");

  // Inspect a document and its chunks.
  await firstHit.getByRole("button").click();
  const sheet = page.getByRole("dialog");
  await expect(sheet.getByRole("heading", { name: "Services | Northwind Labs" })).toBeVisible();
  await expect(sheet.getByText("Copyright Northwind Labs")).toHaveCount(0);
  await sheet.getByRole("tab", { name: /Chunks/ }).click();
  // Short sections are merged into one chunk; each keeps its sub-heading inline.
  const chunks = sheet.getByRole("tabpanel").getByRole("listitem");
  await expect(chunks.getByText(/^AI agents for operations/)).toBeVisible();
  await expect(chunks.getByText(/Custom software development/)).toBeVisible();
  await shot(page, "kb-04-document");
  await page.keyboard.press("Escape");

  // Add knowledge that isn't on the website.
  await page.getByRole("button", { name: "Add document" }).click();
  await page.getByLabel("Title").fill("Case study: Harbour Freight");
  await page.getByLabel("Content").fill(
    "## Result\n\nHarbour Freight cut invoice processing time by 70% after we deployed an AI agent.",
  );
  await page.getByRole("button", { name: "Add document", exact: true }).last().click();
  await expect(page.getByText("Document added to knowledge")).toBeVisible();
  await page.getByLabel("Search the knowledge base").fill("Harbour Freight results");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page.getByRole("search").locator("..").getByRole("listitem").first()).toContainText(
    "Case study: Harbour Freight",
  );

  // Exclude a page: it disappears from search and is marked excluded.
  await page.getByRole("button", { name: "Actions for About | Northwind Labs" }).click();
  await page.getByRole("menuitem", { name: "Exclude" }).click();
  await expect(page.getByText("Excluded from knowledge")).toBeVisible();
  await page.getByRole("tab", { name: "Excluded" }).click();
  await expect(page.getByRole("button", { name: "About | Northwind Labs", exact: true })).toBeVisible();
  await shot(page, "kb-05-excluded");

  // A re-crawl skips unchanged pages.
  await page.getByRole("button", { name: "Crawl website" }).click();
  await page.getByRole("button", { name: "Start crawl" }).click();
  await expect(page.getByText(/Crawl finished: 0 pages indexed, 2 unchanged/)).toBeVisible({
    timeout: 45_000,
  });
});
