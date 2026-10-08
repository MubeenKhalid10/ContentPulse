"use client";

import { CheckCircle2Icon, MessageSquareWarningIcon, XCircleIcon } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { COMMENT_KIND_LABEL } from "@/lib/approvals";
import { timeAgo } from "@/lib/format";
import type { ReviewSummary } from "@/types/api";

/** The latest review decision and its comments, for whoever has to act on it. */
export function ReviewBanner({ review, children }: { review: ReviewSummary | null; children?: React.ReactNode }) {
  if (!review || review.status === "pending") return null;
  const decisions = review.comments.filter((c) => c.kind !== "resubmitted");
  const title = {
    changes_requested: `Changes requested (round ${review.round})`,
    approved: "Approved",
    rejected: "Rejected",
  }[review.status];
  const Icon = { changes_requested: MessageSquareWarningIcon, approved: CheckCircle2Icon, rejected: XCircleIcon }[review.status];

  return (
    <Alert variant={review.status === "rejected" ? "destructive" : "default"} className="mb-6">
      <Icon />
      <AlertTitle>
        {title}
        {review.reviewer && ` by ${review.reviewer.name ?? review.reviewer.email}`}
        {review.reviewed_at && `, ${timeAgo(review.reviewed_at)}`}
      </AlertTitle>
      <AlertDescription className="grid gap-2">
        {decisions.length > 0 && (
          <ul className="grid gap-1.5">
            {decisions.map((c, i) => (
              <li key={i} className="rounded-md bg-background/60 px-3 py-2 text-sm text-foreground">
                <span className="text-xs text-muted-foreground">
                  {c.author?.name ?? c.author?.email ?? "Reviewer"} {COMMENT_KIND_LABEL[c.kind]}:
                </span>
                <p className="whitespace-pre-wrap">{c.body}</p>
              </li>
            ))}
          </ul>
        )}
        {children}
      </AlertDescription>
    </Alert>
  );
}
