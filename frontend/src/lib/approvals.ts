import type { ApprovalStage, ApprovalStatus, ReviewComment } from "@/types/api";

const STAGE_NAME: Record<ApprovalStage, string> = { copy: "content", design: "design" };

/** "Waiting for content approval", "Design approved", ... */
export function approvalStatusLabel(status: ApprovalStatus, stage: ApprovalStage): string {
  const name = STAGE_NAME[stage];
  const Name = name[0].toUpperCase() + name.slice(1);
  switch (status) {
    case "pending":
      return `Waiting for ${name} approval`;
    case "approved":
      return `${Name} approved`;
    case "changes_requested":
      return `${Name} changes requested`;
    case "rejected":
      return `${Name} rejected`;
  }
}

export const COMMENT_KIND_LABEL: Record<ReviewComment["kind"], string> = {
  comment: "commented",
  approved: "approved",
  changes_requested: "requested changes",
  rejected: "rejected",
  resubmitted: "resubmitted",
};
