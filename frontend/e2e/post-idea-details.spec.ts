import { expect, type Page, test } from "@playwright/test";

/**
 * Clicking a post idea opens a pop-up with stored facts only: the idea, the
 * trend's real headlines that match it, and the website passages it cites.
 * The trend data is served by the test (no internet, no AI calls).
 */

const PASSWORD = "correct-horse-battery"; // same test-only value as backend/tests/conftest.py
const ID = "00000000-0000-4000-8000-0000000000bb";
const now = new Date().toISOString();

async function signUp(page: Page) {
  await page.goto("/register");
  await page.getByLabel("Full name").fill("Ida Idea");
  await page.getByLabel("Work email").fill(`e2e-idea-${Date.now()}@example.com`);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/onboarding/);
  await page.getByLabel("Organization name").fill("Idea Co");
  await page.getByRole("button", { name: "Create organization" }).click();
  await expect(page).toHaveURL(/\/dashboard/);
  await page.getByRole("button", { name: "Skip tour" }).click();
}

const mention = (n: number, title: string, description: string, url: string | null) => ({
  id: `00000000-0000-4000-8000-00000000020${n}`,
  source: n % 2 ? "hacker_news" : "reddit",
  title,
  description,
  source_url: url,
  author: null,
  location: "USA",
  category: null,
  published_at: now,
  detected_at: now,
  last_seen_at: now,
  engagement: 100 - n,
  engagement_label: `${100 - n} points`,
  growth_indicator: null,
});

const detail = {
  id: ID,
  topic: "Small language models",
  title: "Small language models",
  description: null,
  keywords: ["slm"],
  category: "AI",
  locations: ["USA"],
  sources: ["hacker_news", "reddit"],
  status: "new",
  first_seen_at: now,
  last_seen_at: now,
  mention_count: 5,
  opportunity_score: 72,
  signals: {},
  relevance_level: "relevant",
  relevance_overridden: false,
  analyzed_at: now,
  relevance_confidence: 0.8,
  analysis: null,
  topic_id: null,
  alignment: {
    engine: "ai",
    classification: "relevant",
    confidence: 0.8,
    reason: "Fits your AI consulting [K1].",
    possible_angles: [
      {
        title: "Cut inference costs with on-device models",
        angle: "Show how running models on-device lowers cloud costs [K1].",
        platforms: ["linkedin"],
        evidence: ["K1"],
      },
    ],
    passages: [
      {
        ref: "K1",
        chunk_id: "c1",
        document_id: "d1",
        title: "Services",
        url: "https://idea.example.com/services",
        heading: "AI cost audits",
        excerpt: "We audit cloud AI spend and move workloads on-device.",
      },
      {
        ref: "K2",
        chunk_id: "c2",
        document_id: "d2",
        title: "About",
        url: "https://idea.example.com/about",
        heading: "Our team",
        excerpt: "Uncited passage that must not appear.",
      },
    ],
  },
  mentions: [
    mention(1, "Hiring trends in AI startups", "Unrelated to the idea.", "https://news.example.com/hiring"),
    mention(2, "On-device models slash inference costs", "Teams report lower cloud bills.", "https://reddit.example.com/costs"),
    mention(3, "Phi-5 runs on a laptop", "Small models on-device.", "javascript:alert(1)"),
    mention(4, "A conference schedule", "Nothing related.", "https://news.example.com/conf"),
  ],
};

test("a post idea opens a pop-up with the trend's own facts", async ({ page }) => {
  await signUp(page);
  await page.route(`**/api/v1/trends/${ID}`, (route) => route.fulfill({ json: detail }));
  await page.goto(`/trends/${ID}`);

  const idea = page.getByRole("button", { name: "Details of the idea “Cut inference costs with on-device models”" });
  await idea.click();

  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("heading", { name: "Cut inference costs with on-device models" })).toBeVisible();
  await expect(dialog.getByText("Show how running models on-device lowers cloud costs.")).toBeVisible();
  // The backdrop is blurred.
  const overlay = page.locator('[data-slot="dialog-overlay"]');
  await expect(overlay).toHaveCSS("backdrop-filter", /blur/);

  // The trend's own headlines, the ones matching the idea first.
  const fromTrend = dialog.locator("section").first();
  const headlines = fromTrend.getByRole("listitem");
  // Only headlines that match the idea (unrelated ones are left out).
  await expect(headlines).toHaveCount(2);
  await expect(headlines.nth(0)).toContainText("On-device models slash inference costs");
  await expect(headlines.nth(0)).toContainText("Teams report lower cloud bills.");
  await expect(headlines.nth(1)).toContainText("Phi-5 runs on a laptop");
  await expect(dialog.getByRole("link", { name: "On-device models slash inference costs" })).toHaveAttribute(
    "href",
    "https://reddit.example.com/costs",
  );
  await expect(dialog.getByRole("link", { name: "Phi-5 runs on a laptop" })).toHaveCount(0);
  await expect(dialog.getByText("Hiring trends in AI startups")).toHaveCount(0);

  // Only the passages the idea cites.
  await expect(dialog.getByText("From your website")).toBeVisible();
  await expect(dialog.getByRole("link", { name: "AI cost audits" })).toHaveAttribute(
    "href",
    "https://idea.example.com/services",
  );
  await expect(dialog.getByText("Uncited passage that must not appear.")).toHaveCount(0);

  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
});

test("on a topic page, Why it's trending starts closed and post ideas open the pop-up", async ({ page }) => {
  await signUp(page);
  const TOPIC_ID = "00000000-0000-4000-8000-0000000000cc";
  const topic = {
    id: TOPIC_ID,
    trend_id: ID,
    title: "Small language models",
    summary: null,
    relevance_level: "relevant",
    matched_services: [],
    recommended_platforms: ["linkedin"],
    status: "shortlisted",
    opportunity_score: 72,
    strategy_count: 0,
    approved_strategy_count: 0,
    created_at: now,
    updated_at: now,
    relevance_reason: null,
    suggested_angles: [],
    target_audience: null,
    platform_fit: [],
    unsupported_claims: [],
    reviewed_at: null,
    trend: detail,
    strategies: [],
  };
  await page.route(`**/api/v1/topics/${TOPIC_ID}`, (route) => route.fulfill({ json: topic }));
  await page.goto(`/topics/${TOPIC_ID}`);

  const why = page.getByRole("button", { name: /Why it's trending/ });
  await expect(why).toHaveAttribute("aria-expanded", "false");
  await expect(page.getByText("Organization fit", { exact: true })).toHaveCount(0);
  await why.click();
  await expect(why).toHaveAttribute("aria-expanded", "true");

  await page.getByRole("button", { name: "Details of the idea “Cut inference costs with on-device models”" }).click();
  await expect(page.getByRole("dialog").getByText("On-device models slash inference costs")).toBeVisible();
});
