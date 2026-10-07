import type { DashboardSummary, Permission } from "@/types/api";

/**
 * The five steps a post moves through. The sidebar, dashboard and welcome
 * tour all describe the product with this one list, so a new user learns a
 * single mental model: trend → topic → post → design → approval.
 */
export interface WorkflowStep {
  n: number;
  href: string;
  label: string;
  /** What you do on this step, in a few words. */
  summary: string;
  permission: Permission;
}

export const WORKFLOW: WorkflowStep[] = [
  { n: 1, href: "/trends", label: "Trends", summary: "Spot what's rising and shortlist what fits", permission: "trends.read" },
  { n: 2, href: "/topics", label: "Topics", summary: "Shortlist topics and plan a post per platform", permission: "topics.read" },
  { n: 3, href: "/content", label: "Content studio", summary: "Write and edit the posts", permission: "content.read" },
  { n: 4, href: "/design", label: "Design", summary: "Add the visual and submit for approval", permission: "design.read" },
  { n: 5, href: "/approvals", label: "Approvals", summary: "Admins approve: the post is ready to publish", permission: "approval.read" },
];

export interface StepCount {
  value: number;
  label: string;
}

/** The counts shown under each step on the dashboard. */
export function stepCounts(s: DashboardSummary): Record<string, StepCount[]> {
  return {
    "/trends": [
      { value: s.relevant_trends, label: "relevant" },
      { value: s.trends_today, label: "new" },
    ],
    "/topics": [
      { value: s.topics_to_review, label: "to review" },
      { value: s.shortlisted_topics, label: "shortlisted" },
    ],
    "/content": [{ value: s.drafts, label: s.drafts === 1 ? "draft" : "drafts" }],
    "/design": [{ value: s.design_pending, label: "in design" }],
    "/approvals": [
      { value: s.pending_approval, label: "waiting" },
      { value: s.approved, label: "ready to publish" },
    ],
  };
}

export interface NextAction {
  title: string;
  detail: string;
  href: string;
  cta: string;
}

/**
 * The single most useful thing to do now, read from the dashboard counts:
 * work closest to publishing first, then work waiting on a decision.
 */
export function nextAction(s: DashboardSummary, can: (p: Permission) => boolean): NextAction {
  const plural = (n: number, one: string, many: string) => (n === 1 ? one : many);
  if (s.pending_approval > 0 && can("approval.manage")) {
    return {
      title: `${s.pending_approval} ${plural(s.pending_approval, "post is", "posts are")} waiting for your approval`,
      detail: "Check the copy and the design, then approve or ask for changes.",
      href: "/approvals",
      cta: "Review posts",
    };
  }
  if (s.design_pending > 0 && can("design.upload")) {
    return {
      title: `${s.design_pending} ${plural(s.design_pending, "post needs", "posts need")} a design`,
      detail: "Each task has a brief, the post copy and your brand rules. Upload the design and submit it for approval.",
      href: "/design",
      cta: "Open design tasks",
    };
  }
  if (s.topics_to_review > 0 && can("topics.manage")) {
    return {
      title: `${s.topics_to_review} ${plural(s.topics_to_review, "topic is", "topics are")} ready for a decision`,
      detail: "Shortlist the ones worth posting about; skip the rest.",
      href: "/topics",
      cta: "Review topics",
    };
  }
  if (s.drafts > 0 && can("content.edit")) {
    return {
      title: `${s.drafts} ${plural(s.drafts, "draft is", "drafts are")} in progress`,
      detail: "Finish the copy, then send each post to design.",
      href: "/content",
      cta: "Open drafts",
    };
  }
  if (s.shortlisted_topics > 0 && can("topics.manage")) {
    return {
      title: "Turn your shortlisted topics into posts",
      detail: "Open a topic, plan a post for a platform, and write it straight from the plan.",
      href: "/topics",
      cta: "Go to topics",
    };
  }
  if (s.relevant_trends > 0) {
    return {
      title: `${s.relevant_trends} ${plural(s.relevant_trends, "trend matches", "trends match")} your organization`,
      detail: "Shortlist the ones you'd like to post about.",
      href: "/trends",
      cta: "See trends",
    };
  }
  if (!can("trends.read")) {
    // Roles without Trends wait for work to reach their step.
    return can("design.upload")
      ? {
          title: "No design tasks right now",
          detail: "Posts appear in Design as soon as someone sends one to design.",
          href: "/design",
          cta: "Open design tasks",
        }
      : {
          title: "Nothing needs you right now",
          detail: "New work shows up here when it reaches your step.",
          href: "/content",
          cta: "See posts",
        };
  }
  return {
    title: "Find out what's trending in your market",
    detail: "Trends are collected on a schedule, or run discovery now from the Trends page.",
    href: "/trends",
    cta: "Go to trends",
  };
}
