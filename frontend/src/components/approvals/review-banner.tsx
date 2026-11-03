"use client";

import { CheckCircle2Icon, MessageSquareWarningIcon, XCircleIcon } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { approvalStatusLabel, COMMENT_KIND_LABEL } from "@/lib/approvals";
import { timeAgo } from "@/lib/format";
import type { ChangeRequest, ReviewSummary } from "@/types/api";

/** The latest review decision and its comments, for whoever has to act on it. */
export function ReviewBanner({
  review,
  request,
  children,
}: {
  review: ReviewSummary | null;
  /** The open change request, when there is one: shown in this same box, never in a second one. */
  request?: ChangeRequest | null;
  children?: React.ReactNode;
}) {
  if (!review || review.status === "pending") return null;
  const decisions = review.comments.filter((c) => c.kind !== "resubmitted");
  // A content review has no design attached; a design review always has one.
  const stage = review.creative_version == null ? "copy" : "design";
  const title =
    review.status === "changes_requested"
      ? `${approvalStatusLabel(review.status, stage)} (round ${review.round})`
      : approvalStatusLabel(review.status, stage);
  const Icon = { changes_requested: MessageSquareWarningIcon, approved: CheckCircle2Icon, rejected: XCircleIcon }[review.status];

  if (review.status === "changes_requested" && request) {
    const admin = request.requested_by?.name ?? request.requested_by?.email ?? "An admin";
    // Anything said in this round beyond the instructions themselves.
    const others = decisions.filter((c) => c.body.trim() !== (request.note ?? "").trim());
    return (
      <Alert className="mb-6" data-testid="change-request">
        <MessageSquareWarningIcon />
        <AlertTitle>{title}</AlertTitle>
        <AlertDescription className="grid gap-3">
          <section className="grid gap-1">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Requested by</h3>
            <p className="text-sm text-foreground">
              {admin}, {timeAgo(request.created_at)}
            </p>
          </section>
          {request.note && (
            <section className="grid gap-1">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">What to change</h3>
              <p className="whitespace-pre-wrap rounded-md bg-background/60 px-3 py-2 text-sm text-foreground">
                {request.note}
              </p>
            </section>
          )}
          {others.length > 0 && (
            <section className="grid gap-1">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">More from this review</h3>
              <ul className="grid gap-1.5">
                {others.map((c, i) => (
                  <li key={i} className="rounded-md bg-background/60 px-3 py-2 text-sm text-foreground">
                    <span className="text-xs text-muted-foreground">
                      {c.author?.name ?? c.author?.email ?? "Reviewer"} {COMMENT_KIND_LABEL[c.kind]}:
                    </span>
                    <p className="whitespace-pre-wrap">{c.body}</p>
                  </li>
                ))}
              </ul>
            </section>
          )}
          {children && (
            <p className="text-sm font-medium text-foreground">Make the changes above, then resubmit for approval.</p>
          )}
          {children}
        </AlertDescription>
      </Alert>
    );
  }

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
        {review.status === "changes_requested" && children && (
          <p className="text-sm font-medium text-foreground">Make the changes above, then resubmit for approval.</p>
        )}
        {children}
      </AlertDescription>
    </Alert>
  );
}
