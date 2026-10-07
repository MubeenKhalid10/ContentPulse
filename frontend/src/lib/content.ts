import type { DesignFormat, PostStatus } from "@/types/api";

export const POST_STATUS_LABEL: Record<PostStatus, string> = {
  draft: "Draft",
  content_review: "Draft",
  design_pending: "Needs design",
  design_in_progress: "In design",
  design_uploaded: "Design added",
  pending_approval: "Waiting for approval",
  changes_requested: "Changes needed",
  approved: "Ready to publish",
  final: "Ready to publish",
  rejected: "Rejected",
  archived: "Archived",
};

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
export function fullText(hook?: string | null, body?: string | null, cta?: string | null, hashtags: string[] = []) {
  const parts = [hook, body, cta].map((p) => p?.trim()).filter(Boolean) as string[];
  if (hashtags.length) parts.push(hashtags.join(" "));
  return parts.join("\n\n");
}
