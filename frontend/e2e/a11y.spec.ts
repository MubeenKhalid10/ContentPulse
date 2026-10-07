import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

/**
 * Accessibility smoke test: every main page, light and dark, has no serious
 * or critical axe violations (WCAG 2.2 A/AA rules).
 */

const PASSWORD = "correct-horse-battery";

const PUBLIC_PAGES = ["/", "/login", "/register", "/forgot-password"];
const APP_PAGES = [
  "/dashboard",
  "/trends",
  "/topics",
  "/content",
  "/design",
  "/approvals",
  "/organization/profile",
  "/organization/services",
  "/organization/brand",
  "/organization/platforms",
  "/organization/knowledge",
  "/team",
  "/settings",
  "/activity",
];

async function expectNoSeriousViolations(page: Page, label: string) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  const serious = results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${v.id}: ${v.help} (${v.nodes.map((n) => n.target.join(" ")).slice(0, 3).join(", ")})`);
  expect(serious, `${label} has accessibility violations`).toEqual([]);
}

for (const scheme of ["light", "dark"] as const) {
  test.describe(`${scheme} mode`, () => {
    test.use({ colorScheme: scheme, reducedMotion: "reduce" });

    test("public pages", async ({ page }) => {
      for (const path of PUBLIC_PAGES) {
        await page.goto(path);
        await page.locator("main").first().waitFor();
        await expectNoSeriousViolations(page, `${path} (${scheme})`);
      }
    });

    test("app pages", async ({ page }) => {
      const email = `e2e-a11y-${scheme}-${Date.now()}@example.com`;
      const reg = await page.request.post("/api/v1/auth/register", {
        data: { email, password: PASSWORD, full_name: "Alex Access" },
      });
      expect(reg.ok()).toBeTruthy();
      const { access_token: token } = await reg.json();
      const org = await page.request.post("/api/v1/organizations", {
        data: { name: `A11y ${scheme}` },
        headers: { Authorization: `Bearer ${token}` },
      });
      expect(org.ok()).toBeTruthy();

      await page.goto("/dashboard");
      await page.getByRole("button", { name: "Skip tour" }).click();
      for (const path of APP_PAGES) {
        await page.goto(path);
        await page.getByRole("heading", { level: 1 }).first().waitFor();
        await page.waitForLoadState("networkidle");
        await expectNoSeriousViolations(page, `${path} (${scheme})`);
      }
    });
  });
}
