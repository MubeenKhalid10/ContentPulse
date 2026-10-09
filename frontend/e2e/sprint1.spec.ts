import { expect, type Page, test } from "@playwright/test";

/**
 * Sprint 1 journey: sign up, create an organization, manage it, invite a
 * teammate, and confirm RBAC + audit history in the UI.
 */

// Same test-only password as backend/tests/conftest.py.
const PASSWORD = "correct-horse-battery";
const run = Date.now();
const ADMIN = `e2e-admin-${run}@example.com`;
const DESIGNER = `e2e-creator-${run}@example.com`;
const SHOTS = process.env.E2E_SCREENSHOTS;

async function shot(page: Page, name: string) {
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true });
}

async function pick(page: Page, trigger: string | RegExp, option: string) {
  await page.getByRole("combobox", { name: trigger }).click();
  await page.getByRole("option", { name: option, exact: true }).click();
}

test("admin sets up an organization and invites a creator", async ({ page, browser }) => {
  // Unauthenticated users are sent to login.
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/login\?next=%2Fdashboard/);
  await shot(page, "01-login");

  // Register → onboarding.
  await page.getByRole("link", { name: "Create an account" }).click();
  await page.getByLabel("Full name").fill("Ada Admin");
  await page.getByLabel("Work email").fill(ADMIN);
  await page.getByLabel("Password").fill("short");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByText("Use at least 10 characters.")).toBeVisible();
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/onboarding/);

  await page.getByLabel("Organization name").fill("Acme Software");
  await page.getByLabel("Website").fill("not a url");
  await page.getByRole("button", { name: "Create organization" }).click();
  await expect(page.getByText(/Enter a full URL/)).toBeVisible();
  await page.getByLabel("Website").fill("https://acme.example.com");
  await page.getByLabel("Industry").fill("Software development");
  await shot(page, "02-onboarding");
  await page.getByRole("button", { name: "Create organization" }).click();

  // Dashboard.
  await expect(page).toHaveURL(/\/dashboard/);
  // First visit: a three-step welcome tour, shown once.
  const tour = page.getByRole("dialog");
  await expect(tour.getByRole("heading", { name: "Welcome to ContentPulse" })).toBeVisible();
  await expect(tour.getByRole("list", { name: "The workflow" }).getByRole("listitem")).toHaveCount(5);
  await shot(page, "03a-welcome-tour");
  await tour.getByRole("button", { name: "Next" }).click();
  await tour.getByRole("button", { name: "Next" }).click();
  await expect(tour.getByRole("heading", { name: "Follow the numbered steps" })).toBeVisible();
  await tour.getByRole("button", { name: "Get started" }).click();
  await expect(tour).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole("heading", { name: "Welcome back, Ada" })).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0); // never shown twice
  await expect(page.getByRole("link", { name: "Start setup" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Content pipeline" })).toBeVisible();
  await expect(page.getByText("0 of 7 done.")).toBeVisible();
  await shot(page, "03-dashboard");

  // Profile.
  await page.getByRole("link", { name: "Profile" }).first().click();
  await page.getByLabel("What you do").fill("We build custom software and AI automation for mid-size companies.");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText("Organization profile saved")).toBeVisible();

  // Services.
  await page.getByRole("link", { name: "Services & products" }).first().click();
  await expect(page.getByText("No services yet")).toBeVisible();
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await page.getByLabel("Name").fill("AI Solutions");
  await page.getByLabel("Category").fill("AI");
  await page.getByLabel("Description").fill("Agents and automation that remove manual work.");
  await page.getByRole("dialog").getByRole("button", { name: "Add", exact: true }).click();
  await expect(page.getByText("Agents and automation that remove manual work.")).toBeVisible();
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await pick(page, "Type", "Product");
  await page.getByLabel("Name").fill("Workflow Automator");
  await page.getByRole("dialog").getByRole("button", { name: "Add", exact: true }).click();
  await expect(page.getByRole("cell", { name: "Product" })).toBeVisible();
  await page.getByRole("switch", { name: "Workflow Automator active" }).click();
  await expect(page.getByRole("switch", { name: "Workflow Automator active" })).not.toBeChecked();
  await shot(page, "04-services");

  // Logo: upload the real file; it's what AI images will carry.
  await page.getByRole("link", { name: "Profile" }).first().click();
  // 1200×1200: the preview must show the whole logo inside its 224×96 box.
  await page.getByLabel("Logo file").setInputFiles("e2e/fixtures/site/big-logo.png");
  await expect(page.getByText("Logo uploaded")).toBeVisible();
  const uploaded = page.getByRole("img", { name: "Your logo" });
  await expect(uploaded).toBeVisible();
  const logoBox = (await uploaded.boundingBox())!;
  const frameBox = (await uploaded.locator("..").boundingBox())!;
  expect(logoBox.width).toBeLessThanOrEqual(frameBox.width);
  expect(logoBox.height).toBeLessThanOrEqual(frameBox.height);
  expect(logoBox.y).toBeGreaterThanOrEqual(frameBox.y);
  expect(logoBox.y + logoBox.height).toBeLessThanOrEqual(frameBox.y + frameBox.height);
  await expect(page.getByText("Uploaded file", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Replace logo" })).toBeVisible();

  // Brand.
  await page.getByRole("link", { name: "Brand" }).first().click();
  await page.getByLabel("Brand voice").fill("Expert but approachable. We explain, we don't lecture.");
  await page.getByLabel("Forbidden terms").fill("synergy");
  await page.getByLabel("Forbidden terms").press("Enter");
  await page.getByLabel("Forbidden terms").fill("disrupt");
  await page.getByLabel("Forbidden terms").press("Enter");
  await expect(page.getByRole("button", { name: "Remove synergy" })).toBeVisible();
  // Where the real logo goes on AI images (default: bottom right).
  const logoSpot = page.getByRole("group", { name: "Logo on AI-generated images" });
  await expect(logoSpot.getByRole("radio", { name: "Bottom right" })).toBeChecked();
  await logoSpot.getByRole("radio", { name: "Top left" }).check({ force: true });
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText("Brand profile saved")).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("group", { name: "Logo on AI-generated images" }).getByRole("radio", { name: "Top left" }),
  ).toBeChecked();
  await shot(page, "05-brand");

  // Content setup: audience, platforms and discovery on one page, one save.
  await page.getByRole("link", { name: "Content setup" }).click();
  await page.getByLabel("Target markets").fill("USA");
  await page.getByLabel("Target markets").press("Enter");
  await page.getByLabel("Target markets").fill("UK");
  await page.getByLabel("Target markets").press("Enter");
  await page.getByRole("button", { name: "LinkedIn" }).click();
  await page.getByRole("button", { name: "X", exact: true }).click();
  await pick(page, "How Often to Check for New Trends", "Every 6 hours");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText("Content setup saved")).toBeVisible();
  await page.reload();
  await expect(page.getByRole("button", { name: "LinkedIn" })).toHaveAttribute("aria-pressed", "true");
  await shot(page, "06-settings");

  // Settings is now about you: name, password, theme, workspaces.
  await page.getByRole("link", { name: "Settings" }).click();
  await expect(page.getByLabel("Email")).toHaveValue(ADMIN);
  await page.getByLabel("Name", { exact: true }).fill("Ada Admin-Lovelace");
  await page.getByRole("button", { name: "Save name" }).click();
  await expect(page.getByText("Your name was saved")).toBeVisible();
  await expect(page.getByRole("list", { name: "Your workspaces" })).toContainText("Acme Software");
  await page.getByRole("radio", { name: "Dark" }).click();
  await expect(page.locator("html")).toHaveClass(/dark/);
  await page.getByRole("radio", { name: "Light" }).click();
  await shot(page, "06b-account");

  // Team: invite a creator.
  await page.getByRole("link", { name: "Team" }).first().click();
  await page.getByRole("button", { name: "Invite" }).click();
  await page.getByLabel("Email").fill(DESIGNER);
  await pick(page, "Role", "Creator");
  await page.getByRole("button", { name: "Send invite" }).click();
  const inviteUrl = await page.getByRole("textbox", { name: "Invite link" }).inputValue();
  expect(inviteUrl).toMatch(/\/invite\//);
  await shot(page, "07-invite");
  await page.getByRole("button", { name: "Done" }).click();
  await expect(page.getByText("Invited", { exact: true })).toBeVisible();

  // The creator accepts in a separate browser context.
  const designerContext = await browser.newContext();
  const designer = await designerContext.newPage();
  await designer.goto(inviteUrl);
  await expect(designer.getByRole("heading", { name: "Join Acme Software" })).toBeVisible();
  await shot(designer, "08-accept-invite");
  await designer.getByLabel("Your name").fill("Dee Designer");
  await designer.getByLabel("Choose a password").fill(PASSWORD);
  await designer.getByRole("button", { name: "Join Acme Software" }).click();
  await expect(designer).toHaveURL(/\/dashboard/);

  // RBAC in the UI: a creator sees brand read-only and no activity log.
  await designer.goto("/organization/brand");
  await expect(designer.getByText("Only admins can make changes.")).toBeVisible();
  await expect(designer.getByLabel("Brand voice")).toBeDisabled();
  await expect(designer.getByRole("link", { name: "Activity log" })).toHaveCount(0);
  await shot(designer, "09-designer-readonly");
  await designerContext.close();

  // Admin sees the creator as active and the full audit trail.
  await page.reload();
  await expect(page.getByText("Dee Designer")).toBeVisible();
  await page.getByRole("link", { name: "Activity log" }).click();
  // Grouped by day, filterable by area.
  await expect(page.getByRole("heading", { name: /^Today/ })).toBeVisible();
  await expect(page.getByText("joined the team")).toBeVisible();
  await expect(page.getByText("updated the brand profile")).toBeVisible();
  await pick(page, "Show changes to", "Team");
  await expect(page.getByText("joined the team")).toBeVisible();
  await expect(page.getByText("updated the brand profile")).toHaveCount(0);
  await pick(page, "Show changes to", "Everything");
  await shot(page, "10-activity");

  // Sign out returns to login and protects the app again.
  await page.getByRole("button", { name: /Acme Software/ }).click();
  await page.getByRole("menuitem", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login/);
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/login/);
});
