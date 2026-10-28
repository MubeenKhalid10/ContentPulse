"use client";

import { z } from "zod";

import type {
  Platform,
  SearchIntent,
  Strategy,
  StrategyDetails,
  StrategySuggestion,
} from "@/types/api";

export const text = (max: number) => z.string().trim().max(max, `Keep it under ${max} characters.`);

const lines = (value: string) =>
  value
    .split(/\n|,/)
    .map((v) => v.trim())
    .filter(Boolean);

export const INTENT_OPTIONS: { value: SearchIntent; label: string }[] = [
  { value: "informational", label: "Informational" },
  { value: "commercial", label: "Commercial" },
  { value: "transactional", label: "Transactional" },
  { value: "navigational", label: "Navigational" },
];

export const schema = z.object({
  platform: z.enum(["linkedin", "x", "instagram", "facebook", "blog"]),
  post_type: z.string().trim().min(1, "Choose a post type."),
  objective: text(120),
  content_angle: text(2000).min(1, "Describe the post idea."),
  target_audience: text(2000),
  hook_direction: text(2000),
  cta_direction: text(2000),
  tone: text(120),
  recommended_format: text(60),
  rationale: text(2000),
  // Blog only: the SEO plan.
  seo_title: text(120),
  primary_keyword: text(80),
  secondary_keywords: z
    .string()
    .refine((v) => lines(v).length <= 15, "Up to 15 keywords.")
    .refine((v) => lines(v).every((k) => k.length <= 80), "Keep each keyword under 80 characters."),
  search_intent: z.string(),
  outline: z
    .string()
    .refine((v) => v.split("\n").filter((h) => h.trim()).length <= 15, "Up to 15 sections.")
    .refine((v) => v.split("\n").every((h) => h.trim().length <= 200), "Keep each heading under 200 characters."),
  target_word_count: z
    .string()
    .trim()
    .refine((v) => !v || (/^\d+$/.test(v) && +v >= 300 && +v <= 6000), "Between 300 and 6,000 words."),
  featured_image_direction: text(2000),
});

export type Values = z.infer<typeof schema>;

/** Placeholder post type when several platforms are planned at once; each gets its own default. */
export const AUTO_POST_TYPE = "auto";

const FIELDS = [
  "objective",
  "content_angle",
  "target_audience",
  "hook_direction",
  "cta_direction",
  "tone",
  "recommended_format",
  "rationale",
] as const;

export function toValues(platform: Platform, s?: Partial<Strategy | StrategySuggestion>, audience?: string | null): Values {
  return {
    platform,
    post_type: s?.post_type ?? "",
    objective: s?.objective ?? "",
    content_angle: s?.content_angle ?? "",
    target_audience: s?.target_audience ?? audience ?? "",
    hook_direction: s?.hook_direction ?? "",
    cta_direction: s?.cta_direction ?? "",
    tone: s?.tone ?? "",
    recommended_format: s?.recommended_format ?? "",
    rationale: s?.rationale ?? "",
    seo_title: s?.details?.seo_title ?? "",
    primary_keyword: s?.details?.primary_keyword ?? "",
    secondary_keywords: (s?.details?.secondary_keywords ?? []).join(", "),
    search_intent: s?.details?.search_intent ?? "",
    outline: (s?.details?.outline ?? []).join("\n"),
    target_word_count: s?.details?.target_word_count ? String(s.details.target_word_count) : "",
    featured_image_direction: s?.details?.featured_image_direction ?? "",
  };
}

function toDetails(values: Values): StrategyDetails | null {
  if (values.platform !== "blog") return null;
  return {
    seo_title: values.seo_title || null,
    primary_keyword: values.primary_keyword || null,
    secondary_keywords: lines(values.secondary_keywords),
    search_intent: (values.search_intent || null) as SearchIntent | null,
    outline: values.outline
      .split("\n")
      .map((h) => h.trim())
      .filter(Boolean),
    target_word_count: values.target_word_count ? Number(values.target_word_count) : null,
    featured_image_direction: values.featured_image_direction || null,
  };
}

/** Empty strings become null so optional fields stay empty in the API. */
export function toBody(values: Values) {
  return {
    platform: values.platform,
    post_type: values.post_type,
    ...(Object.fromEntries(FIELDS.map((f) => [f, values[f] || null])) as Record<(typeof FIELDS)[number], string | null>),
    details: toDetails(values),
  };
}
