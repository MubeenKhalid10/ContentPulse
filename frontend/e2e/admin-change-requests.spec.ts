import { expect, type Page, test } from "@playwright/test";

/**
 * Only an admin requests changes. A creator reads the request on the post, redoes the work
 * and resubmits; there is no way to ask an admin to reopen locked work. Post data is served
 * by the test (the rules are covered by backend/tests/test_admin_change_requests.py).
 */

const PASSWORD = "correct-horse-battery"; // same test-only value as backend/tests/conftest.py
const POST = "00000000-0000-4000-8000-000000000ca1";
const REVIEW = "00000000-0000-4000-8000-000000000ca2";
const TASK = "00000000-0000-4000-8000-000000000ca3";
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

/** The admin's request for a design change, not yet redone. */
const changeRequest = {
  id: REVIEW,
  post_id: POST,
  scope: "design",
  note: "Fix the typo on slide 3.",
  status: "open",
  requested_by: { id: "u1", name: "Ada Admin", email: "ada@example.com" },
  created_at: now,
  content_done: true, // not asked for
  design_done: false,
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

test("a creator reads the admin's request with its progress, and cannot ask for one", async ({ page }) => {
  await signUp(page);
  await asCreator(page);
  await servePost(page, () =>
    postDetail({
      status: "changes_requested",
      editable: true,
      change_request: changeRequest,
      review: { ...review, status: "changes_requested" },
    }),
  );

  await page.goto(`/content/${POST}`);
  await expect(page.getByRole("link", { name: "Approvals" })).toHaveCount(0);
  const notice = page.getByTestId("change-request");
  await expect(notice.getByRole("heading", { name: "Requested by" })).toBeVisible();
  await expect(notice).toContainText("Ada Admin");
  await expect(notice.getByRole("heading", { name: "What to change" })).toBeVisible();
  await expect(notice).toContainText("Fix the typo on slide 3.");
  await expect(notice.getByRole("list")).toHaveCount(0); // no progress checklist
  await expect(page.getByRole("button", { name: /Request a change/ })).toHaveCount(0);
});

test("the creator's list tabs are named for what the admin asked", async ({ page }) => {
  await signUp(page);
  await asCreator(page);
  await page.goto("/content");
  await expect(page.getByRole("tab", { name: /Content Change Requests/ })).toBeVisible();
  await page.goto("/design");
  await expect(page.getByRole("tab", { name: /Design Change Requests/ })).toBeVisible();
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
  expect(asked).toBe(false);
});

test("Approvals has Pending Approvals and Review History, and no creator requests", async ({ page }) => {
  await signUp(page);
  await page.route(/\/api\/v1\/approvals\?/, (route) =>
    route.fulfill({
      json: {
        items: [],
        total: 0,
        counts: { pending: 0, reviewed: 0, approved: 0, changes_requested: 0, rejected: 0, all: 0 },
        stage_pending: { copy: 0, design: 0 },
        ready_count: 0,
      },
    }),
  );
  await page.goto("/approvals");
  await expect(page.getByRole("tab", { name: /Pending Approvals/ })).toBeVisible();
  await expect(page.getByRole("tab", { name: /Review History/ })).toBeVisible();
  await expect(page.getByRole("tab", { name: /Change requests/i })).toHaveCount(0);
  await page.getByRole("tab", { name: /Review History/ }).click();
  await expect(page.getByRole("tab", { name: /Review History/ })).toHaveAttribute("aria-selected", "true");
});

test("an admin requests changes from the post, with real instructions", async ({ page }) => {
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
  await expect(dialog.getByRole("radio", { name: /^Both/ })).toHaveCount(0);
  await dialog.getByRole("radio", { name: /^Content/ }).click();
  const send = dialog.getByRole("button", { name: "Request changes" });
  await dialog.getByLabel("What should change").fill("Too short");
  await expect(send).toBeDisabled(); // instructions must be meaningful
  await dialog.getByLabel("What should change").fill("New headline and image.");
  await send.click();

  await expect(page.getByText("Changes requested", { exact: true })).toBeVisible();
  expect(sent).toEqual({ comment: "New headline and image.", scope: "copy" });
});

test("a decision someone else already made shows the reason and reloads", async ({ page }) => {
  await signUp(page);
  let loads = 0;
  await servePost(page, () => {
    loads += 1;
    return postDetail();
  });
  await page.route(`**/api/v1/approvals/${REVIEW}/reopen`, (route) =>
    route.fulfill({
      status: 409,
      json: { error: { code: "INVALID_STATE_TRANSITION", message: "This submission has already been reviewed." } },
    }),
  );
  await page.goto(`/content/${POST}`);
  const before = loads;
  await page.getByRole("button", { name: "Request changes" }).click();
  const dialog = page.getByRole("alertdialog");
  await dialog.getByLabel("What should change").fill("New headline and image.");
  await dialog.getByRole("button", { name: "Request changes" }).click();

  await expect(page.getByText("This submission has already been reviewed.")).toBeVisible();
  await expect(dialog).toHaveCount(0); // closed, not stuck
  await expect.poll(() => loads).toBeGreaterThan(before); // the post reloaded
});

test("the notification bell shows what happened and opens it", async ({ page }) => {
  await signUp(page);
  await asCreator(page);
  let read = false;
  await servePost(page, () => postDetail());
  await page.route("**/api/v1/notifications?**", (route) =>
    route.fulfill({
      json: {
        unread: read ? 0 : 1,
        items: [
          {
            id: "00000000-0000-4000-8000-000000000ca6",
            post_id: POST,
            kind: "changes_requested",
            scope: "design",
            title: "An admin asked for changes to A finished post (design)",
            body: "Shorten the headline.",
            link: `/content/${POST}`,
            read_at: read ? now : null,
            created_at: now,
          },
        ],
      },
    }),
  );
  await page.route("**/api/v1/notifications/*/read", (route) => {
    read = true;
    return route.fulfill({ status: 204 });
  });
  await page.goto("/dashboard");
  await page.getByRole("button", { name: /Notifications, 1 unread/ }).first().click();
  await page.getByText("An admin asked for changes to A finished post").click();
  await expect(page).toHaveURL(new RegExp(`/content/${POST}`));
  expect(read).toBe(true);
});
