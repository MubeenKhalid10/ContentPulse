import { LOGO_POSITIONS } from "@/lib/logo";
import { z } from "zod";

/** Optional text: blank input is sent as null so the backend clears the field. */
export const optionalText = (max = 10_000) =>
  z
    .string()
    .trim()
    .max(max, `Use at most ${max} characters.`)
    .transform((v) => (v === "" ? null : v));

export const optionalUrl = z
  .string()
  .trim()
  .refine((v) => v === "" || /^https?:\/\/\S+\.\S+/i.test(v), "Enter a full URL, e.g. https://example.com")
  .transform((v) => (v === "" ? null : v));

const name = z.string().trim().min(1, "Enter a name.").max(200);

export const organizationSchema = z.object({
  name,
  website_url: optionalUrl,
  industry: optionalText(120),
  timezone: z.string().min(1),
  description: optionalText(),
});

export const organizationProfileSchema = organizationSchema.extend({
  logo_url: optionalUrl,
});

export const serviceSchema = z.object({
  kind: z.enum(["service", "product", "expertise"]),
  name,
  category: optionalText(120),
  description: optionalText(),
  active: z.boolean(),
});

export const brandSchema = z.object({
  brand_voice: optionalText(),
  tone: optionalText(),
  writing_style: optionalText(),
  preferred_terms: z.array(z.string()),
  forbidden_terms: z.array(z.string()),
  content_guidelines: optionalText(),
  cta_guidelines: optionalText(),
  hashtag_guidelines: optionalText(),
  brand_colors: z.array(z.string()),
  typography: optionalText(),
  logo_position: z.enum(LOGO_POSITIONS),
});

export const settingsSchema = z.object({
  default_language: z.string().min(1),
  default_timezone: z.string().min(1),
  target_markets: z.array(z.string()),
  target_audience: optionalText(),
  content_goals: z.array(z.string()),
  enabled_platforms: z.array(z.enum(["linkedin", "x", "instagram", "facebook", "blog"])),
  tracked_keywords: z.array(z.string()),
  subreddits: z.array(z.string().regex(/^(r\/)?[A-Za-z0-9_]{2,21}$/, "Use subreddit names like r/automation.")),
  rss_feeds: z.array(z.string().regex(/^https?:\/\/\S+\.\S+/i, "Feeds must be full URLs (https://…)")),
  trend_frequency: z.enum(["manual", "hourly", "every_6_hours", "daily"]),
});

export const inviteSchema = z.object({
  email: z.email("Enter a valid email address."),
  role: z.enum(["admin", "creator", "viewer"]),
});
