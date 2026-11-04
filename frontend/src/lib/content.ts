import { PLATFORM_LABEL } from "@/lib/topics";
import type { DesignFormat, Platform, PostStatus } from "@/types/api";

/** Status tags. Each says in words where the post is (color is a hint only),
 * and content vs design approval are never both called "approval". */
export const POST_STATUS_LABEL: Record<PostStatus, string> = {
  draft: "Draft",
  content_review: "Waiting for content approval",
  design_pending: "Waiting for a designer",
  design_in_progress: "Design in progress",
  design_uploaded: "Design uploaded, not yet submitted",
  pending_approval: "Waiting for design approval",
  // Design approval sending the post back; postStatusLabel names what was sent back.
  changes_requested: "Changes requested",
  approved: "Design approved, almost ready to publish",
  final: "Ready to publish",
  rejected: "Rejected",
  archived: "Archived",
};

const CHANGES_LABEL = {
  copy: "Content changes requested",
  design: "Design changes requested",
} as const;

/** What a change is about, in words: a "content change", the "design". */
export const SCOPE_NAME: Record<keyof typeof CHANGES_LABEL, string> = {
  copy: "content",
  design: "design",
};

/** The tag for an admin's change request: what was asked for. */
export function changeRequestLabel(request: { scope: keyof typeof CHANGES_LABEL }) {
  return CHANGES_LABEL[request.scope];
}

/** The status tag, naming what was sent back (the copy or the design) when it can. */
export function postStatusLabel(post: { status: PostStatus; changes_scope?: keyof typeof CHANGES_LABEL | null }) {
  return post.changes_scope ? CHANGES_LABEL[post.changes_scope] : POST_STATUS_LABEL[post.status];
}

export const DESIGN_FORMAT_LABEL: Record<DesignFormat, string> = {
  text_only: "Text only",
  single_image: "Single image",
  carousel: "Carousel",
  infographic: "Infographic",
  video: "Video",
  reel: "Reel",
};

export const DESIGN_FORMAT_OPTIONS = (Object.keys(DESIGN_FORMAT_LABEL) as DesignFormat[]).map((value) => ({
  value,
  label: DESIGN_FORMAT_LABEL[value],
}));

export const META_TITLE_MAX = 60;
export const META_DESCRIPTION_MAX = 160;
export const SLUG_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

/** URL slug, matching the backend's: lowercase ASCII words joined by hyphens. */
export function slugify(text: string, limit = 80) {
  let slug = text
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  if (slug.length > limit) slug = slug.slice(0, limit).replace(/-[^-]*$/, "");
  return slug;
}

export function wordCount(...parts: (string | null | undefined)[]) {
  return parts.join(" ").match(/\b\w+\b/g)?.length ?? 0;
}

/** The post as it would be published; matches the backend's length check. */
/** Why this copy can't be sent for approval: it is over the admin's limits for the platform. */
export function copyLimitProblems(
  copy: { hook?: string | null; body?: string | null; cta?: string | null; hashtags: string[] } | null | undefined,
  limits: { max_length: number | null; hashtag_limit: number | null },
  platform: Platform,
): string[] {
  if (!copy) return [];
  const label = PLATFORM_LABEL[platform];
  const problems: string[] = [];
  const length = fullText(copy.hook, copy.body, copy.cta, copy.hashtags).length;
  if (limits.max_length != null && length > limits.max_length) {
    problems.push(
      `${length.toLocaleString()} characters: ${(length - limits.max_length).toLocaleString()} over the ${label} limit of ${limits.max_length.toLocaleString()}.`,
    );
  }
  // Blog posts carry no hashtags in the editor, so only the length limit applies there.
  if (platform !== "blog" && limits.hashtag_limit != null && copy.hashtags.length > limits.hashtag_limit) {
    problems.push(
      `${copy.hashtags.length} hashtags: ${label} allows ${limits.hashtag_limit}.`,
    );
  }
  return problems;
}

export function fullText(hook?: string | null, body?: string | null, cta?: string | null, hashtags: string[] = []) {
  const parts = [hook, body, cta].map((p) => p?.trim()).filter(Boolean) as string[];
  if (hashtags.length) parts.push(hashtags.join(" "));
  return parts.join("\n\n");
}
