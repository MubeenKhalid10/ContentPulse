import type {
  ApprovalStatus,
  DesignTaskStatus,
  Platform,
  PostStatus,
  RelevanceLevel,
  StrategyStatus,
  TopicStatus,
} from "@/types/api";

/**
 * One color vocabulary for every tag in the app, so a color always means the
 * same thing:
 *   green   done / strongest      teal    good / our brand
 *   blue    new, not started      sky     seen, under way
 *   amber   needs a decision      orange  sent back
 *   violet  waiting on someone    red     rejected / failed
 *   neutral inactive, archived
 * Platforms use their own recognizable hues.
 */
export type Tone =
  | "neutral"
  | "teal"
  | "green"
  | "blue"
  | "sky"
  | "indigo"
  | "violet"
  | "amber"
  | "orange"
  | "red"
  | "pink"
  | "ink";

/** Soft tint + readable text + hairline ring, tuned for light and dark mode. */
export const TONE_CLASS: Record<Tone, string> = {
  neutral: "bg-muted text-muted-foreground ring-border",
  teal: "bg-teal-50 text-teal-800 ring-teal-200 dark:bg-teal-950/60 dark:text-teal-200 dark:ring-teal-800/70",
  green: "bg-emerald-50 text-emerald-800 ring-emerald-200 dark:bg-emerald-950/60 dark:text-emerald-200 dark:ring-emerald-800/70",
  blue: "bg-blue-50 text-blue-800 ring-blue-200 dark:bg-blue-950/60 dark:text-blue-200 dark:ring-blue-800/70",
  sky: "bg-sky-50 text-sky-800 ring-sky-200 dark:bg-sky-950/60 dark:text-sky-200 dark:ring-sky-800/70",
  indigo: "bg-indigo-50 text-indigo-800 ring-indigo-200 dark:bg-indigo-950/60 dark:text-indigo-200 dark:ring-indigo-800/70",
  violet: "bg-violet-50 text-violet-800 ring-violet-200 dark:bg-violet-950/60 dark:text-violet-200 dark:ring-violet-800/70",
  amber: "bg-amber-50 text-amber-800 ring-amber-200 dark:bg-amber-950/60 dark:text-amber-200 dark:ring-amber-800/70",
  orange: "bg-orange-50 text-orange-800 ring-orange-200 dark:bg-orange-950/60 dark:text-orange-200 dark:ring-orange-800/70",
  red: "bg-red-50 text-red-800 ring-red-200 dark:bg-red-950/60 dark:text-red-200 dark:ring-red-800/70",
  pink: "bg-pink-50 text-pink-800 ring-pink-200 dark:bg-pink-950/60 dark:text-pink-200 dark:ring-pink-800/70",
  ink: "bg-zinc-900 text-white ring-zinc-900 dark:bg-zinc-100 dark:text-zinc-900 dark:ring-zinc-100",
};

/** Small dot in the same hue, for tags that lead with one. */
export const TONE_DOT: Record<Tone, string> = {
  neutral: "bg-muted-foreground/50",
  teal: "bg-teal-600",
  green: "bg-emerald-600",
  blue: "bg-blue-600",
  sky: "bg-sky-600",
  indigo: "bg-indigo-600",
  violet: "bg-violet-600",
  amber: "bg-amber-500",
  orange: "bg-orange-500",
  red: "bg-red-600",
  pink: "bg-pink-600",
  ink: "bg-white dark:bg-zinc-900",
};

export const RELEVANCE_TONE: Record<RelevanceLevel, Tone> = {
  highly_relevant: "green",
  relevant: "teal",
  weakly_relevant: "amber",
  not_relevant: "neutral",
};

export const PLATFORM_TONE: Record<Platform, Tone> = {
  linkedin: "blue",
  x: "ink",
  instagram: "pink",
  facebook: "indigo",
  blog: "teal",
};

export const TREND_STATUS_TONE: Record<string, Tone> = {
  new: "blue",
  analyzed: "sky",
  shortlisted: "green",
  rejected: "red",
  archived: "neutral",
};

export const TOPIC_STATUS_TONE: Record<TopicStatus, Tone> = {
  new: "blue",
  reviewed: "sky",
  shortlisted: "green",
  rejected: "red",
  archived: "neutral",
};

export const STRATEGY_STATUS_TONE: Record<StrategyStatus, Tone> = {
  draft: "amber",
  approved: "green",
  archived: "neutral",
};

export const POST_STATUS_TONE: Record<PostStatus, Tone> = {
  draft: "neutral",
  content_review: "sky",
  design_pending: "violet",
  design_in_progress: "amber",
  design_uploaded: "indigo",
  pending_approval: "violet",
  changes_requested: "orange",
  approved: "green",
  final: "green",
  rejected: "red",
  archived: "neutral",
};

export const TASK_STATUS_TONE: Record<DesignTaskStatus, Tone> = {
  open: "blue",
  assigned: "sky",
  in_progress: "amber",
  submitted: "violet",
  completed: "green",
  cancelled: "neutral",
};

export const APPROVAL_STATUS_TONE: Record<ApprovalStatus, Tone> = {
  pending: "violet",
  approved: "green",
  changes_requested: "orange",
  rejected: "red",
};

/** Platform dot that reads on a plain background (the ink dot is for inside an ink tag). */
export const PLATFORM_DOT: Record<Platform, string> = {
  linkedin: TONE_DOT.blue,
  x: "bg-zinc-900 dark:bg-zinc-100",
  instagram: TONE_DOT.pink,
  facebook: TONE_DOT.indigo,
  blog: TONE_DOT.teal,
};

/** Selected-tab tint per platform, matching PlatformTag. */
export const PLATFORM_TAB_ACTIVE: Record<Platform, string> = {
  linkedin:
    "data-active:bg-blue-50 data-active:text-blue-800 data-active:ring-blue-200 dark:data-active:bg-blue-950/60 dark:data-active:text-blue-200 dark:data-active:ring-blue-800/70",
  x: "data-active:bg-zinc-900 data-active:text-white! data-active:ring-zinc-900 dark:data-active:bg-zinc-100 dark:data-active:text-zinc-900! dark:data-active:ring-zinc-100",
  instagram:
    "data-active:bg-pink-50 data-active:text-pink-800 data-active:ring-pink-200 dark:data-active:bg-pink-950/60 dark:data-active:text-pink-200 dark:data-active:ring-pink-800/70",
  facebook:
    "data-active:bg-indigo-50 data-active:text-indigo-800 data-active:ring-indigo-200 dark:data-active:bg-indigo-950/60 dark:data-active:text-indigo-200 dark:data-active:ring-indigo-800/70",
  blog: "data-active:bg-teal-50 data-active:text-teal-800 data-active:ring-teal-200 dark:data-active:bg-teal-950/60 dark:data-active:text-teal-200 dark:data-active:ring-teal-800/70",
};
