import type { Platform, StrategyStatus, TopicStatus } from "@/types/api";

export const PLATFORM_LABEL: Record<Platform, string> = {
  linkedin: "LinkedIn",
  x: "X",
  instagram: "Instagram",
  facebook: "Facebook",
  blog: "Blog",
};

export const TOPIC_STATUS_LABEL: Record<TopicStatus, string> = {
  new: "New",
  reviewed: "Reviewed",
  shortlisted: "Shortlisted",
  rejected: "Rejected",
  archived: "Archived",
};

export const STRATEGY_STATUS_LABEL: Record<StrategyStatus, string> = {
  draft: "Draft",
  approved: "Approved",
  archived: "Archived",
};

export const STRATEGY_SOURCE_LABEL = {
  ai: "Drafted by AI",
  rules: "Drafted from your playbook",
  manual: "Written by your team",
} as const;
