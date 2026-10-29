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

interface FieldIssue {
  field: string;
  message: string;
  in?: string;
}

/** "String should have at most 60 characters" → "is too long (up to 60 characters)". */
function plainIssue(message: string): string {
  const max = /at most (\d+) (character|item)/.exec(message);
  if (max) return `is too long (up to ${max[1]} ${max[2]}s)`;
  if (/at least 1 (character|item)/.test(message)) return "can't be empty";
  const min = /at least (\d+) (character|item)/.exec(message);
  if (min) return `is too short (at least ${min[1]} ${min[2]}s)`;
  if (message === "Field required") return "is required";
  const le = /less than or equal to ([\d.]+)/.exec(message);
  if (le) return `must be ${le[1]} or less`;
  const ge = /greater than or equal to ([\d.]+)/.exec(message);
  if (ge) return `must be ${ge[1]} or more`;
  if (/valid email/i.test(message)) return "isn't a valid email address";
  if (/valid URL/i.test(message)) return "isn't a valid web address";
  if (/^Input should be /.test(message)) return "has a value that isn't allowed";
  return message.replace(/^Value error, /, "").replace(/\.$/, "");
}

const fieldName = (field: string) => {
  const last = field.split(".").filter((p) => !/^\d+$/.test(p)).pop() ?? field;
  const name = last.replace(/_/g, " ");
  return name.charAt(0).toUpperCase() + name.slice(1);
};

/**
 * What went wrong, in words a person can act on. The API's own messages are already written
 * for people; its generic ones ("Request validation failed.", "An unexpected error occurred.")
 * and bare status codes are not, so those are replaced here, once, for every screen.
 */
function friendlyMessage(status: number, code: string, message: string | undefined, details: unknown): string {
  if (code === "VALIDATION_ERROR" && Array.isArray(details) && details.length) {
    const issues = details as FieldIssue[];
    // A bad URL or query is the app's fault, not something the person typed.
    if (issues.some((d) => d.in && d.in !== "body")) {
      return "Something went wrong loading this. Refresh the page and try again; if it keeps happening, contact support.";
    }
    const [first] = issues;
    const more = issues.length > 1 ? ` (and ${issues.length - 1} more)` : "";
    return `Please check what you entered: ${fieldName(first.field)} ${plainIssue(first.message)}${more}.`;
  }
  const generic = !message || message === "Request validation failed." || message === "An unexpected error occurred.";
  if (!generic) return message;
  if (status === 401) return "Your session has ended. Sign in again to continue.";
  if (status === 403) return "You don't have permission to do this. Ask an admin if you need access.";
  if (status === 404) return "This item couldn't be found. It may have been deleted.";
  if (status === 409) return "This changed while you were working on it. Refresh the page and try again.";
  if (status === 413) return "This file is too large to upload.";
  if (status === 422) return "Some of the details aren't valid. Check what you entered and try again.";
  if (status === 429) return "Too many requests in a short time. Wait a moment and try again.";
  if (status === 502 || status === 503 || status === 504) {
    return "The server is busy or restarting. Wait a moment and try again.";
  }
  return "Something went wrong on our side. Try again in a moment; if it keeps happening, contact support.";
}

async function failure(response: Response): Promise<ApiError> {
  const error = (await response.json().catch(() => null))?.error;
  const code = error?.code ?? "INTERNAL_ERROR";
  return new ApiError(
    response.status,
    code,
    friendlyMessage(response.status, code, error?.message, error?.details),
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

/** Largest page the list endpoints accept (`limit` is capped at 100 server side). */
const MAX_PAGE = 100;

/**
 * A list endpoint's first `limit` items. "Show more" grows `limit` past what one request may
 * ask for (asking for 150 got a 422), so larger amounts are fetched in pages and joined.
 */
export async function apiList<T extends { items: unknown[] }>(path: string, params: URLSearchParams): Promise<T> {
  const limit = Number(params.get("limit") ?? MAX_PAGE);
  let page = null as T | null;
  for (let offset = 0; offset < limit; offset += MAX_PAGE) {
    const next = new URLSearchParams(params);
    next.set("limit", String(Math.min(MAX_PAGE, limit - offset)));
    if (offset) next.set("offset", String(offset));
    const result: T = await api<T>(`${path}?${next}`);
    page = page ? { ...page, items: [...page.items, ...result.items] } : result;
    if (result.items.length < MAX_PAGE) break;
  }
  return page!;
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  // Browser errors ("Failed to fetch", "Load failed") mean nothing to people.
  if (error instanceof TypeError) return "Cannot reach the server. Check your connection and try again.";
  if (error instanceof Error && error.message) return error.message;
  return "Something went wrong. Please try again.";
}
