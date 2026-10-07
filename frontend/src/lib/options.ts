import type { Option } from "@/components/shared/simple-select";
import { SOURCE_NAMES } from "@/lib/trends";
import type { OfferingKind, Platform, Role, TrendFrequency } from "@/types/api";

export const ROLE_OPTIONS: Option<Role>[] = [
  { value: "admin", label: "Admin" },
  { value: "creator", label: "Creator" },
  { value: "viewer", label: "Viewer" },
];

export const ROLE_DESCRIPTIONS: Record<Role, string> = {
  admin: "Everything, including approving posts, organization settings and the team.",
  creator: "Shortlists topics, writes posts, adds the design and sends them to an admin for approval.",
  viewer: "Sees everything and can share finished posts. Can't change anything.",
};

export const PLATFORM_OPTIONS: Option<Platform>[] = [
  { value: "linkedin", label: "LinkedIn" },
  { value: "x", label: "X" },
  { value: "instagram", label: "Instagram" },
  { value: "facebook", label: "Facebook" },
  { value: "blog", label: "Blog" },
];

export const SOURCE_OPTIONS: Option[] = Object.entries(SOURCE_NAMES).map(([value, label]) => ({
  value,
  label,
}));

export const FREQUENCY_OPTIONS: Option<TrendFrequency>[] = [
  { value: "hourly", label: "Every hour" },
  { value: "every_6_hours", label: "Every 6 hours" },
  { value: "daily", label: "Once a day" },
  { value: "manual", label: "Only when I ask" },
];

export const OFFERING_KIND_OPTIONS: Option<OfferingKind>[] = [
  { value: "service", label: "Service" },
  { value: "product", label: "Product" },
  { value: "expertise", label: "Expertise" },
];

export const LANGUAGE_OPTIONS: Option[] = [
  { value: "en", label: "English" },
  { value: "es", label: "Spanish" },
  { value: "fr", label: "French" },
  { value: "de", label: "German" },
  { value: "pt", label: "Portuguese" },
  { value: "ar", label: "Arabic" },
  { value: "ur", label: "Urdu" },
];

let timezones: Option[] | undefined;

export function timezoneOptions(): Option[] {
  if (!timezones) {
    const zones: string[] =
      typeof Intl.supportedValuesOf === "function" ? Intl.supportedValuesOf("timeZone") : [];
    timezones = ["UTC", ...zones.filter((z) => z !== "UTC")].map((z) => ({
      value: z,
      label: z.replaceAll("_", " "),
    }));
  }
  return timezones;
}

export function browserTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

export function roleLabel(role: Role) {
  return ROLE_OPTIONS.find((r) => r.value === role)?.label ?? role;
}
