import { expect, type Page, test } from "@playwright/test";

/**
 * A network drop while the sign-in token is being renewed must not sign anyone
 * out. Only Supabase saying the session is over may do that.
 */

const SUPABASE = "https://fakeproject.supabase.co";
const COOKIE = "sb-fakeproject-auth-token";
const ORG = "00000000-0000-4000-8000-0000000000c1";

const me = {
  id: "00000000-0000-4000-8000-0000000000c2",
  email: "dana@example.com",
  name: "Dana Drop",
  organization_id: ORG,
  role: "admin",
  permissions: [],
  memberships: [{ organization_id: ORG, organization_name: "Drop Co", role: "admin" }],
};

const session = (expiresAt: number) => ({
  access_token: "header.payload.signature",
  refresh_token: "refresh-token",
  token_type: "bearer",
  expires_in: 3600,
  expires_at: expiresAt,
  user: { id: me.id, email: me.email, aud: "authenticated", app_metadata: {}, user_metadata: {}, created_at: "2026-01-01T00:00:00Z" },
});

/** A signed-in browser whose access token has already expired, against a stand-in API. */
async function signedInWithExpiredToken(page: Page) {
  const hour = Math.floor(Date.now() / 1000) - 3600;
  await page.context().addCookies([
    { name: COOKIE, value: encodeURIComponent(JSON.stringify(session(hour))), url: "http://localhost:3001" },
  ]);
  await page.route("**/api/v1/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/auth/config")) {
      return route.fulfill({
        json: { provider: "supabase", supabase_url: SUPABASE, supabase_anon_key: "sb_publishable_test" },
      });
    }
    // Like the real API: no token, no entry.
    if (!route.request().headers().authorization) {
      return route.fulfill({
        status: 401,
        json: { error: { code: "UNAUTHORIZED", message: "Authentication required." } },
      });
    }
    if (path.endsWith("/auth/me")) return route.fulfill({ json: me });
    return route.fulfill({ status: 404, json: { error: { code: "NOT_FOUND", message: "Not found." } } });
  });
}

const hasSession = async (page: Page) =>
  (await page.context().cookies()).some((c) => c.name.startsWith(COOKIE));

test("a network drop during token renewal keeps you signed in", async ({ page }) => {
  // The Supabase client keeps retrying a failed renewal for up to 30 seconds.
  test.setTimeout(240_000);
  await signedInWithExpiredToken(page);
  let online = false;
  await page.route(`${SUPABASE}/**`, (route) =>
    online
      ? route.fulfill({ json: session(Math.floor(Date.now() / 1000) + 3600) })
      : route.abort("namenotresolved"),
  );

  await page.goto("/dashboard");
  await expect(page.getByText("We couldn't load your workspace")).toBeVisible({ timeout: 60_000 });
  expect(page.url()).not.toContain("/login");
  expect(await hasSession(page)).toBe(true);

  // Reconnects without a click, even though the client won't renew for a minute after a failure.
  online = true;
  await expect(page.getByText("We couldn't load your workspace")).toHaveCount(0, { timeout: 100_000 });
  expect(page.url()).toContain("/dashboard");
});

test("a session Supabase has ended still signs you out", async ({ page }) => {
  await signedInWithExpiredToken(page);
  await page.route(`${SUPABASE}/**`, (route) =>
    route.fulfill({
      status: 400,
      json: { code: "refresh_token_not_found", error_code: "refresh_token_not_found", msg: "Invalid Refresh Token" },
    }),
  );

  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/login/, { timeout: 30_000 });
});
