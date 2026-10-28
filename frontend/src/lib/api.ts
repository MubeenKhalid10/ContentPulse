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

/**
 * Each tab keeps its own active organization (sessionStorage), so switching
 * client workspaces in one tab can never redirect another tab's writes. The
 * last choice is also remembered across tabs (localStorage) only as the
 * starting point for a tab that has no choice of its own yet.
 */
export function getActiveOrgId(): string | null {
  try {
    const own = window.sessionStorage.getItem(ACTIVE_ORG_KEY);
    if (own) return own;
    const lastUsed = window.localStorage.getItem(ACTIVE_ORG_KEY);
    if (lastUsed) window.sessionStorage.setItem(ACTIVE_ORG_KEY, lastUsed);
    return lastUsed;
  } catch {
    return null;
  }
}

export function setActiveOrgId(id: string | null) {
  try {
    if (id) {
      window.sessionStorage.setItem(ACTIVE_ORG_KEY, id);
      window.localStorage.setItem(ACTIVE_ORG_KEY, id);
    } else {
      window.sessionStorage.removeItem(ACTIVE_ORG_KEY);
      window.localStorage.removeItem(ACTIVE_ORG_KEY);
    }
  } catch {
    // Storage unavailable (private mode): fall back to the backend default org.
  }
}

type Method = "GET" | "POST" | "PATCH" | "PUT" | "DELETE";

/** The active organization and, in Supabase mode, the access token. */
async function contextHeaders(): Promise<Record<string, string>> {
  const headers: Record<string, string> = {};
  const orgId = typeof window !== "undefined" ? getActiveOrgId() : null;
  if (orgId) headers["X-Organization-Id"] = orgId;
  if (typeof window !== "undefined") {
    // Supabase mode: send the Supabase access token. Local mode uses the
    // httpOnly session cookie instead (token is null).
    const token = await supabaseAccessToken().catch(() => null);
    if (token) headers.Authorization = `Bearer ${token}`;
  }
  return headers;
}

async function failure(response: Response): Promise<ApiError> {
  const error = (await response.json().catch(() => null))?.error;
  return new ApiError(
    response.status,
    error?.code ?? "INTERNAL_ERROR",
    error?.message ?? `Request failed (${response.status})`,
    error?.details,
  );
}

export async function api<T>(path: string, options: { method?: Method; body?: unknown } = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json", ...(await contextHeaders()) };
  // A file (Blob) is sent as the raw body with its own type; anything else as JSON.
  const raw = typeof Blob !== "undefined" && options.body instanceof Blob;
  if (raw) headers["Content-Type"] = (options.body as Blob).type || "application/octet-stream";
  else if (options.body !== undefined) headers["Content-Type"] = "application/json";

  let response: Response;
  try {
    response = await fetch(`/api/v1${path}`, {
      method: options.method ?? "GET",
      headers,
      body: raw
        ? (options.body as Blob)
        : options.body !== undefined
          ? JSON.stringify(options.body)
          : undefined,
      credentials: "same-origin",
    });
  } catch {
    throw new ApiError(0, "NETWORK_ERROR", "Cannot reach the server. Check your connection.");
  }

  if (response.status === 204) return undefined as T;
  if (!response.ok) throw await failure(response);
  return (await response.json().catch(() => null)) as T;
}

export interface Download {
  blob: Blob;
  filename: string;
  headers: Headers;
}

/** GET a file (CSV, ...) with the same organization and auth as `api`. */
export async function apiDownload(path: string, accept = "text/csv"): Promise<Download> {
  let response: Response;
  try {
    response = await fetch(`/api/v1${path}`, {
      headers: { Accept: accept, ...(await contextHeaders()) },
      credentials: "same-origin",
    });
  } catch {
    throw new ApiError(0, "NETWORK_ERROR", "Cannot reach the server. Check your connection.");
  }
  if (!response.ok) throw await failure(response);
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const filename = /filename="([^"]+)"/.exec(disposition)?.[1] ?? "download";
  return { blob: await response.blob(), filename, headers: response.headers };
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Something went wrong.";
}
