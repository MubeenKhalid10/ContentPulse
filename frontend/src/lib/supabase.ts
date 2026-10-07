"use client";

import { createBrowserClient } from "@supabase/ssr";
import type { SupabaseClient } from "@supabase/supabase-js";

/**
 * How users sign in is decided by the API (AUTH_PROVIDER in the root .env),
 * fetched once at runtime so the web app needs no separate configuration.
 */
export interface AuthConfig {
  provider: "local" | "supabase";
  supabase_url: string | null;
  supabase_anon_key: string | null;
  /** Local mode: the server can email reset links (SMTP is set up). */
  password_reset?: boolean;
}

let configPromise: Promise<AuthConfig> | null = null;
let client: SupabaseClient | null = null;

export function getAuthConfig(): Promise<AuthConfig> {
  configPromise ??= fetch("/api/v1/auth/config", { headers: { Accept: "application/json" } })
    .then((r) => {
      if (!r.ok) throw new Error(`auth config ${r.status}`);
      return r.json() as Promise<AuthConfig>;
    })
    .catch((error) => {
      configPromise = null; // retry on the next call
      throw error;
    });
  return configPromise;
}

/** The Supabase client in Supabase mode, otherwise null. */
export async function getSupabase(): Promise<SupabaseClient | null> {
  const config = await getAuthConfig();
  if (config.provider !== "supabase" || !config.supabase_url || !config.supabase_anon_key) return null;
  // Session lives in cookies (sb-<ref>-auth-token) so proxy.ts can see it.
  client ??= createBrowserClient(config.supabase_url, config.supabase_anon_key);
  return client;
}

/** Current access token in Supabase mode (refreshed automatically). */
export async function supabaseAccessToken(): Promise<string | null> {
  const supabase = await getSupabase();
  if (!supabase) return null;
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}

/** Same-origin URL Supabase emails link back to (email confirmation, resets). */
export function authRedirect(path: string, next?: string): string {
  const url = new URL(path, window.location.origin);
  if (next) url.searchParams.set("next", next);
  return url.toString();
}

/** Only same-site relative paths are allowed as post-auth destinations. */
export function safeNext(next: string | null | undefined, fallback = "/dashboard"): string {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : fallback;
}

/** Friendlier wording for common Supabase Auth errors. */
export function supabaseErrorMessage(message: string): string {
  const m = message.toLowerCase();
  if (m.includes("invalid login credentials")) return "Invalid email or password.";
  if (m.includes("email not confirmed")) return "Confirm your email first: check your inbox for the link.";
  if (m.includes("already registered")) return "An account with this email already exists. Sign in instead.";
  if (m.includes("rate limit")) return "Too many attempts. Wait a minute and try again.";
  return message;
}
