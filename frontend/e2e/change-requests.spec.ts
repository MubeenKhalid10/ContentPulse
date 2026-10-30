import { expect, type Page, test } from "@playwright/test";

/**
 * Asking for changes happens where the work is, never by a trip to Approvals.
 * Creators ask and an admin decides; Approvals itself is for admins. Post data is
 * served by the test (the rules are covered by backend/tests/test_change_requests.py).
 */

const PASSWORD = "correct-horse-battery"; // same test-only value as backend/tests/conftest.py
const POST = "00000000-0000-4000-8000-000000000ca1";
const REVIEW = "00000000-0000-4000-8000-000000000ca2";
const TASK = "00000000-0000-4000-8000-000000000ca3";
const REQUEST = "00000000-0000-4000-8000-000000000ca4";
const now = new Date().toISOString();

async function signUp(page: Page) {
  await page.goto("/register");
  await page.getByLabel("Full name").fill("Casey Change");
  await page.getByLabel("Work email").fill(`e2e-change-${Date.now()}@example.com`);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/onboarding/);
  await page.getByLabel("Organization name").fill("Change Co");
  await page.getByRole("button", { name: "Create organization" }).click();
  await expect(page).toHaveURL(/\/dashboard/);
  await page.getByRole("button", { name: "Skip tour" }).click();
}

const CREATOR = [
  "organization.read",
  "knowledge.read",
  "trends.read",
  "topics.read",
  "topics.manage",
  "content.read",
  "content.generate",
  "content.edit",
  "design.read",
  "design.upload",
  "design.submit",
];

/** The real signed-in user, with a creator's permissions. */
async function asCreator(page: Page) {
  await page.route("**/api/v1/auth/me", async (route) => {
    const response = await route.fetch();
    const me = await response.json();
    await route.fulfill({ json: { ...me, role: "creator", permissions: CREATOR } });
  });
}

const review = {
  request_id: REVIEW,
  status: "approved",
  round: 1,
  post_version: 1,
  creative_version: 1,
  reviewer: null,
  reviewed_at: now,
  comments: [],
};

const changeRequest = {
  id: REQUEST,
  post_id: POST,
  scope: "design",
  note: "Slide 3 has a typo.",
  status: "pending",
  requested_by: { id: "u2", name: "Cam Creator", email: "cam@example.com" },
  decided_by: null,
  decided_at: null,
  decision_note: null,
  created_at: now,
};

const postDetail = (extra: object = {}) => ({
  id: POST,
  title: "A finished post",
  platform: "linkedin",
  status: "final",
  current_version: 1,
  hook: "Hook",
  topic: null,
  content_strategy_id: null,
  variant_of_id: null,
  generation: null,
  changes_scope: null,
  change_request: null,
  change_request_scopes: ["copy", "design", "both"],
  created_at: now,
  updated_at: now,
  current: {
    id: "00000000-0000-4000-8000-000000000ca5",
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
  limits: { max_length: null, hashtag_limit: null },
  editable: false,
  design_task: { id: TASK, status: "completed" },
  review,
  creatives: [],
  ...extra,
});

async function servePost(page: Page, detail: () => object) {
  await page.route(`**/api/v1/content/${POST}`, (route) => route.fulfill({ json: detail() }));
  await page.route(`**/api/v1/content/${POST}/comments`, (route) => route.fulfill({ json: [] }));
  await page.route(`**/api/v1/content/${POST}/versions`, (route) => route.fulfill({ json: [] }));
}

test("a creator has no Approvals, and asks for a change from the post", async ({ page }) => {
  await signUp(page);
  await asCreator(page);
  let sent: unknown = null;
  await servePost(page, () =>
    postDetail(sent ? { change_request: changeRequest } : {}),
  );
  await page.route(`**/api/v1/content/${POST}/change-requests`, async (route) => {
    sent = route.request().postDataJSON();
    await route.fulfill({ status: 201, json: changeRequest });
  });

  await page.goto(`/content/${POST}`);
  await expect(page.getByRole("link", { name: "Approvals" })).toHaveCount(0);

  await page.getByRole("button", { name: "Request a change" }).click();
  const dialog = page.getByRole("alertdialog");
  await dialog.getByRole("radio", { name: /^Design/ }).click();
  await dialog.getByLabel("What should change and why").fill("Slide 3 has a typo.");
  await dialog.getByRole("button", { name: "Send request" }).click();

  await expect(page.getByText("Sent to an admin")).toBeVisible();
  expect(sent).toEqual({ scope: "design", note: "Slide 3 has a typo." });
  // Still on the post, tagged, and it can't be asked twice.
  expect(new URL(page.url()).pathname).toBe(`/content/${POST}`);
  await expect(page.getByText("Creator requested design change")).toBeVisible();
  await expect(page.getByText("Waiting for an admin to decide.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Request a change" })).toHaveCount(0);
});

test("a creator sees why their request was declined", async ({ page }) => {
  await signUp(page);
  await asCreator(page);
  await servePost(page, () =>
    postDetail({
      change_request: {
        ...changeRequest,
        status: "declined",
        decided_by: { id: "u1", name: "Ada Admin", email: "ada@example.com" },
        decided_at: now,
        decision_note: "Already published",
      },
    }),
  );
  await page.goto(`/content/${POST}`);
  await expect(page.getByText("Creator's design change declined")).toBeVisible();
  await expect(page.getByText("Reason: Already published.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Request a change" })).toBeVisible();
});

test("an old Approvals link tells a creator where to go, without loading approvals", async ({ page }) => {
  await signUp(page);
  await asCreator(page);
  let asked = false;
  await page.route(/\/api\/v1\/approvals/, (route) => {
    asked = true;
    return route.fulfill({ status: 403, json: {} });
  });
  await page.goto(`/approvals/${REVIEW}`);
  await expect(page.getByText("Approvals are for admins")).toBeVisible();
  await expect(page.getByRole("link", { name: "Go to Write posts" })).toBeVisible();
  expect(asked).toBe(false);
});

test("an admin requests changes from the post without leaving it", async ({ page }) => {
  await signUp(page);
  let sent: unknown = null;
  await servePost(page, () => postDetail());
  await page.route(`**/api/v1/approvals/${REVIEW}/reopen`, async (route) => {
    sent = route.request().postDataJSON();
    await route.fulfill({ json: {} });
  });

  await page.goto(`/content/${POST}`);
  await page.getByRole("button", { name: "Request changes" }).click();
  const dialog = page.getByRole("alertdialog");
  await dialog.getByRole("radio", { name: /^Both/ }).click();
  await dialog.getByLabel("What should change").fill("New headline and image.");
  await dialog.getByRole("button", { name: "Request changes" }).click();

  await expect(page.getByText("Changes requested", { exact: true })).toBeVisible();
  expect(sent).toEqual({ comment: "New headline and image.", scope: "both" });
  expect(new URL(page.url()).pathname).toBe(`/content/${POST}`);
});

test("an admin decides a creator's request from the Approvals queue", async ({ page }) => {
  await signUp(page);
  let accepted = false;
  await page.route(/\/api\/v1\/approvals\?/, (route) =>
    route.fulfill({
      json: {
        items: [],
        total: 0,
        counts: { pending: 0, reviewed: 0, approved: 0, changes_requested: 0, rejected: 0, all: 0 },
        stage_pending: { copy: 0, design: 0 },
        ready_count: 0,
        change_request_count: accepted ? 0 : 1,
      },
    }),
  );
  await page.route("**/api/v1/approvals/change-requests?**", (route) =>
    route.fulfill({
      json: accepted
        ? { items: [], total: 0 }
        : {
            items: [
              {
                ...changeRequest,
                post: { id: POST, title: "A finished post", platform: "linkedin", status: "final", current_version: 1 },
                topic_title: null,
              },
            ],
            total: 1,
          },
    }),
  );
  await page.route(`**/api/v1/approvals/change-requests/${REQUEST}/accept`, async (route) => {
    accepted = true;
    await route.fulfill({ json: { ...changeRequest, status: "accepted" } });
  });

  await page.goto("/approvals");
  const tab = page.getByRole("tab", { name: /Change requests/ });
  await expect(tab).toHaveText("Change requests1");
  await tab.click();

  const queue = page.getByRole("list", { name: "Change requests" });
  await expect(queue).toContainText("Slide 3 has a typo.");
  await expect(queue).toContainText("Creator requested design change");
  await queue.getByRole("button", { name: "Accept and reopen" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Accept and reopen" }).click();

  await expect(page.getByText("Reopened for the creator")).toBeVisible();
  await expect(page.getByText("No change requests")).toBeVisible();
  await expect(tab).toHaveText("Change requests");
});
