import type { PostDetail } from "@/types/api";

/**
 * Detail pages remember where they were opened from in a `from` query param,
 * so Back returns there instead of to the section's own list.
 */
const SECTIONS: Record<string, [list: string, detail: string]> = {
  dashboard: ["Dashboard", "Dashboard"],
  trends: ["Trends", "Back to trend"],
  topics: ["Shortlist & plans", "Back to plans"],
  content: ["Write posts", "Back to post"],
  design: ["Design", "Back to design task"],
  approvals: ["Approvals", "Back to review"],
};

/** Only same-site paths are followed (no `//host` or `/\host` tricks). */
export function safeFrom(raw: string | null): string | null {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//") || raw.startsWith("/\\"))
    return null;
  // Browsers strip tabs/newlines and treat `\` as `/`, so also resolve it the
  // way they will and require it to stay on this origin.
  const base = "http://same-origin.invalid";
  try {
    return new URL(raw, base).origin === base ? raw : null;
  } catch {
    return null;
  }
}

export function backLabel(from: string): string {
  const [section, id] = from.split(/[?#]/)[0].split("/").filter(Boolean);
  const names = SECTIONS[section ?? ""];
  if (!names) return "Back";
  return id ? names[1] : names[0];
}

/** `href` with a note of the page it was opened from (`here` is path + query). */
export function withFrom(href: string, here: string): string {
  return `${href}${href.includes("?") ? "&" : "?"}from=${encodeURIComponent(here)}`;
}

/** The page that fits where a post is in the workflow: writing, design or approval. */
export function postStageHref(post: PostDetail): string {
  const studio = `/content/${post.id}`;
  const design = post.design_task ? `/design/${post.design_task.id}` : studio;
  const review = post.review ? `/approvals/${post.review.request_id}` : studio;
  switch (post.status) {
    case "content_review":
    case "pending_approval":
    case "approved":
    case "final":
      return review;
    case "design_pending":
    case "design_in_progress":
    case "design_uploaded":
      return design;
    case "changes_requested":
      // Sent back at the design stage: the designer's task is open again.
      return post.design_task &&
        ["open", "assigned", "in_progress"].includes(post.design_task.status)
        ? design
        : studio;
    default:
      return studio;
  }
}
