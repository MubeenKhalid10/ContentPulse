const relative = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["year", 365 * 24 * 3600],
  ["month", 30 * 24 * 3600],
  ["week", 7 * 24 * 3600],
  ["day", 24 * 3600],
  ["hour", 3600],
  ["minute", 60],
];

export function timeAgo(iso: string, now = Date.now()): string {
  const seconds = (new Date(iso).getTime() - now) / 1000;
  for (const [unit, size] of UNITS) {
    if (Math.abs(seconds) >= size) return relative.format(Math.round(seconds / size), unit);
  }
  return "just now";
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

const ACTIONS: Record<string, string> = {
  ORGANIZATION_CREATED: "created the organization",
  ORGANIZATION_UPDATED: "updated the organization profile",
  SETTINGS_UPDATED: "updated settings",
  BRAND_UPDATED: "updated the brand profile",
  SERVICE_CREATED: "added a service",
  SERVICE_UPDATED: "updated a service",
  SERVICE_DELETED: "removed a service",
  MEMBER_INVITED: "invited a team member",
  MEMBER_JOINED: "joined the team",
  MEMBER_UPDATED: "changed a team member",
  MEMBER_REMOVED: "removed a team member",
  KNOWLEDGE_CRAWL_STARTED: "started a website crawl",
  KNOWLEDGE_CRAWL_CANCELLED: "stopped a website crawl",
  KNOWLEDGE_REINDEX_STARTED: "re-indexed the knowledge base",
  KNOWLEDGE_DOCUMENT_ADDED: "added a knowledge document",
  KNOWLEDGE_DOCUMENT_UPDATED: "updated a knowledge document",
  KNOWLEDGE_DOCUMENT_DELETED: "deleted a knowledge document",
  TREND_SHORTLISTED: "shortlisted a trend",
  TREND_REJECTED: "rejected a trend",
  TREND_RESTORED: "restored a trend",
  STATUS_CHANGED: "changed a status",
  TREND_ANALYSIS_REQUESTED: "requested a trend analysis",
  TREND_RELEVANCE_OVERRIDDEN: "changed a trend's relevance",
  TOPIC_SHORTLISTED: "shortlisted a topic",
  TOPIC_REVIEWED: "reviewed a topic",
  TOPIC_REJECTED: "rejected a topic",
  TOPIC_RESTORED: "restored a topic",
  TOPIC_ARCHIVED: "archived a topic",
  TOPIC_UPDATED: "edited a topic",
  STRATEGY_CREATED: "created a content strategy",
  STRATEGY_UPDATED: "edited a content strategy",
  STRATEGY_APPROVED: "approved a content strategy",
  STRATEGY_REOPENED: "reopened a content strategy",
  STRATEGY_ARCHIVED: "archived a content strategy",
  PLATFORM_RULES_UPDATED: "updated a platform playbook",
  CONTENT_GENERATED: "generated content",
  CONTENT_EDITED: "edited content",
  DESIGN_UPLOADED: "uploaded a design",
  APPROVAL_REQUESTED: "requested approval",
  APPROVAL_COMMENTED: "commented on a submission",
  DESIGN_BRIEF_UPDATED: "edited a design brief",
  DESIGN_TASK_ASSIGNED: "assigned a design task",
  APPROVED: "approved a post",
  CHANGES_REQUESTED: "requested changes",
  REJECTED: "rejected a post",
};

export function describeAction(action: string): string {
  return ACTIONS[action] ?? action.toLowerCase().replaceAll("_", " ");
}

export function humanize(field: string): string {
  const s = field.replaceAll("_", " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}
