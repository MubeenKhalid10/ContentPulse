"use client";

import { MessageSquareWarningIcon, RotateCcwIcon } from "lucide-react";
import { useState } from "react";

import { Tag } from "@/components/shared/tag";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { useCan } from "@/lib/auth";
import { changeRequestLabel, SCOPE_NAME } from "@/lib/content";
import { timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { ApprovalStage, ChangeRequest, ChangeScope, ReviewSummary } from "@/types/api";

import { ChangesDialog } from "./changes-dialog";

export const SCOPES: { value: ChangeScope; label: string; help: string }[] = [
  { value: "copy", label: "Content", help: "The text reopens. The design stays as it is." },
  { value: "design", label: "Design", help: "The design reopens. The text stays locked." },
];

/** Pick what should reopen, from the `allowed` choices. */
export function ScopePicker({
  allowed,
  value,
  onChange,
  disabled,
}: {
  allowed: ChangeScope[];
  value: ChangeScope;
  onChange: (scope: ChangeScope) => void;
  disabled?: boolean;
}) {
  const options = SCOPES.filter((o) => allowed.includes(o.value));
  return (
    <div role="radiogroup" aria-label="What needs changes" className="grid gap-1.5">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          role="radio"
          disabled={disabled}
          aria-checked={value === option.value}
          tabIndex={value === option.value ? 0 : -1}
          onClick={() => onChange(option.value)}
          onKeyDown={(e) => {
            const i = options.findIndex((o) => o.value === value);
            if (e.key === "ArrowRight" || e.key === "ArrowDown") {
              e.preventDefault();
              onChange(options[(i + 1) % options.length].value);
            } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
              e.preventDefault();
              onChange(options[(i + options.length - 1) % options.length].value);
            }
          }}
          className={cn(
            "grid rounded-lg border px-3 py-2 text-left text-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-60",
            value === option.value ? "border-primary bg-primary/5" : "enabled:hover:bg-muted",
          )}
        >
          <span className="font-medium">{option.label}</span>
          <span className="text-xs text-muted-foreground">{option.help}</span>
        </button>
      ))}
    </div>
  );
}

/** The tag for an admin's change request, beside the post's status wherever the post is listed. */
export function ChangeRequestTag({ request }: { request?: ChangeRequest | null }) {
  if (!request) return null;
  return (
    <Tag tone="amber" dot>
      {changeRequestLabel(request)}
    </Tag>
  );
}

/** An admin's Request changes, right where the work is: no trip to the Approvals page. */
export function AdminRequestChanges({ review }: { review: ReviewSummary | null }) {
  const canReview = useCan()("approval.manage");
  const [open, setOpen] = useState(false);
  if (!canReview || !review || (review.status !== "pending" && review.status !== "approved")) return null;
  const stage: ApprovalStage = review.creative_version == null ? "copy" : "design";
  return (
    <>
      <Button size="sm" variant="outline" className="w-fit" onClick={() => setOpen(true)}>
        <RotateCcwIcon />
        Request changes
      </Button>
      <ChangesDialog
        approval={{ id: review.request_id, status: review.status, stage }}
        open={open}
        onOpenChange={setOpen}
      />
    </>
  );
}

/**
 * What an admin asked for, on the post the creator has to change: who asked, the
 * instructions, and Only the admin starts a request; the
 * creator answers by changing the work and resubmitting.
 */
export function ChangeRequestNotice({ request }: { request?: ChangeRequest | null }) {
  if (!request) return null;
  const who = request.requested_by?.name ?? request.requested_by?.email ?? "An admin";
  return (
    <Alert className="mb-6" data-testid="change-request">
      <MessageSquareWarningIcon />
      <AlertTitle>
        {who} requested {SCOPE_NAME[request.scope]} changes, {timeAgo(request.created_at)}
      </AlertTitle>
      <AlertDescription className="grid gap-2">
        {request.note && (
          <p className="whitespace-pre-wrap rounded-md bg-background/60 px-3 py-2 text-sm text-foreground">
            {request.note}
          </p>
        )}
      </AlertDescription>
    </Alert>
  );
}
