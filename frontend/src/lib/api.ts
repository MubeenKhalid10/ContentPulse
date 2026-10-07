/**
 * Thin client for the FastAPI backend. Requests go to /api/v1 on this origin
 * (rewritten to the backend by next.config.ts) and carry the httpOnly session
 * cookie automatically.
 */

import { supabaseAccessToken } from "@/lib/supabase";

const ACTIVE_ORG_KEY = "cp_active_org";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }

  /** Field-level messages from a VALIDATION_ERROR response. */
  get fieldErrors(): Record<string, string> {
    if (!Array.isArray(this.details)) return {};
    return Object.fromEntries(
      (this.details as { field: string; message: string }[]).map((d) => [d.field, d.message]),
    );
  }
}

export function getActiveOrgId(): string | null {
  try {
    return window.localStorage.getItem(ACTIVE_ORG_KEY);
  } catch {
    return null;
  }
}

export function setActiveOrgId(id: string | null) {
  try {
    if (id) window.localStorage.setItem(ACTIVE_ORG_KEY, id);
    else window.localStorage.removeItem(ACTIVE_ORG_KEY);
  } catch {
    // Storage unavailable (private mode): fall back to the backend default org.
  }
}

type Method = "GET" | "POST" | "PATCH" | "PUT" | "DELETE";

export async function api<T>(path: string, options: { method?: Method; body?: unknown } = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  const orgId = typeof window !== "undefined" ? getActiveOrgId() : null;
  if (orgId) headers["X-Organization-Id"] = orgId;
  if (typeof window !== "undefined") {
    // Supabase mode: send the Supabase access token. Local mode uses the
    // httpOnly session cookie instead (token is null).
    const token = await supabaseAccessToken().catch(() => null);
    if (token) headers.Authorization = `Bearer ${token}`;
  }

  let response: Response;
  try {
    response = await fetch(`/api/v1${path}`, {
      method: options.method ?? "GET",
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
      credentials: "same-origin",
    });
  } catch {
    throw new ApiError(0, "NETWORK_ERROR", "Cannot reach the server. Check your connection.");
  }

  if (response.status === 204) return undefined as T;

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const error = payload?.error;
    throw new ApiError(
      response.status,
      error?.code ?? "INTERNAL_ERROR",
      error?.message ?? `Request failed (${response.status})`,
      error?.details,
    );
  }
  return payload as T;
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Something went wrong.";
}
