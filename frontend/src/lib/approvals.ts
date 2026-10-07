import type { ApprovalStatus, ReviewComment } from "@/types/api";

export const APPROVAL_STATUS_LABEL: Record<ApprovalStatus, string> = {
  pending: "Waiting for approval",
  approved: "Approved",
  changes_requested: "Changes needed",
  rejected: "Rejected",
};

export const COMMENT_KIND_LABEL: Record<ReviewComment["kind"], string> = {
  comment: "commented",
  approved: "approved",
  changes_requested: "requested changes",
  rejected: "rejected",
  resubmitted: "resubmitted",
};
