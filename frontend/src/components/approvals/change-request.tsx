"use client";

import { CheckIcon, MessageSquareWarningIcon, RotateCcwIcon, SendIcon, XIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/content/confirm-dialog";
import { Tag } from "@/components/shared/tag";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  useAcceptChangeRequest,
  useCreateChangeRequest,
  useDeclineChangeRequest,
} from "@/hooks/use-approvals";
import { errorMessage } from "@/lib/api";
import { useCan } from "@/lib/auth";
import { changeRequestLabel, SCOPE_NAME } from "@/lib/content";
import { timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { ApprovalStage, ChangeRequest, ChangeScope, ReviewSummary } from "@/types/api";

import { ChangesDialog } from "./changes-dialog";

export const SCOPES: { value: ChangeScope; label: string; help: string }[] = [
  { value: "copy", label: "Content", help: "The text reopens. The design stays as it is." },
  { value: "design", label: "Design", help: "The design reopens. The text stays locked." },
  { value: "both", label: "Both", help: "The text and the design both reopen." },
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

/** The tag for a creator's request, beside the post's status wherever the post is listed. */
export function ChangeRequestTag({ request }: { request?: ChangeRequest | null }) {
  if (!request) return null;
  return (
    <Tag tone={request.status === "pending" ? "amber" : "neutral"} dot>
      {changeRequestLabel(request)}
    </Tag>
  );
}

/** A creator asks an admin to reopen locked work. Only shown when there is something to ask for. */
export function RequestChangeButton({
  postId,
  scopes = [],
  request,
  size = "sm",
}: {
  postId: string;
  scopes?: ChangeScope[];
  request?: ChangeRequest | null;
  size?: "sm" | "default";
}) {
  const can = useCan();
  const create = useCreateChangeRequest();
  const [open, setOpen] = useState(false);
  const [scope, setScope] = useState<ChangeScope>(scopes[0] ?? "copy");
  const [note, setNote] = useState("");
  // Admins reopen work themselves instead of asking.
  if (!can("content.edit") || can("approval.manage")) return null;
  if (!scopes.length || request?.status === "pending") return null;
  const chosen = scopes.includes(scope) ? scope : scopes[0];
  return (
    <>
      <Button size={size} variant="outline" className="w-fit" onClick={() => setOpen(true)}>
        <RotateCcwIcon />
        Request a change
      </Button>
      <AlertDialog open={open} onOpenChange={(next) => !create.isPending && setOpen(next)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Request a change</AlertDialogTitle>
            <AlertDialogDescription>
              An admin decides. Until then the work stays locked and the post keeps its place.
            </AlertDialogDescription>
          </AlertDialogHeader>
          {scopes.length > 1 && (
            <ScopePicker allowed={scopes} value={chosen} onChange={setScope} disabled={create.isPending} />
          )}
          <Textarea
            aria-label="What should change and why"
            rows={4}
            maxLength={4000}
            placeholder="What should change, and why?"
            disabled={create.isPending}
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
          <AlertDialogFooter>
            <AlertDialogCancel disabled={create.isPending}>Cancel</AlertDialogCancel>
            <Button
              disabled={!note.trim() || create.isPending}
              pending={create.isPending}
              onClick={() =>
                create.mutate(
                  { postId, scope: chosen, note: note.trim() },
                  {
                    onSuccess: () => {
                      toast.success("Sent to an admin");
                      setNote("");
                      setOpen(false);
                    },
                    onError: (e) => toast.error(errorMessage(e)),
                  },
                )
              }
            >
              <SendIcon />
              {create.isPending ? "Sending…" : "Send request"}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
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

/** Accept (reopens what was asked for) or decline. */
export function ChangeRequestActions({ request }: { request: ChangeRequest }) {
  const accept = useAcceptChangeRequest();
  const decline = useDeclineChangeRequest();
  const [acceptOpen, setAcceptOpen] = useState(false);
  const [declineOpen, setDeclineOpen] = useState(false);
  const [reason, setReason] = useState("");
  const busy = accept.isPending || decline.isPending;
  const onError = (e: unknown) => toast.error(errorMessage(e));
  return (
    <div className="flex flex-wrap gap-2">
      <Button size="sm" disabled={busy} pending={accept.isPending} onClick={() => setAcceptOpen(true)}>
        <CheckIcon />
        Accept and reopen
      </Button>
      <Button size="sm" variant="outline" disabled={busy} onClick={() => setDeclineOpen(true)}>
        <XIcon />
        Decline
      </Button>
      <ConfirmDialog
        open={acceptOpen}
        onOpenChange={setAcceptOpen}
        title={`Reopen the ${SCOPE_NAME[request.scope]}?`}
        description="The creator can edit it again and must send it back for approval. If it was approved, that approval no longer counts."
        confirmLabel="Accept and reopen"
        pending={accept.isPending}
        onConfirm={() =>
          accept.mutate(request.id, {
            onSuccess: () => toast.success("Reopened for the creator"),
            onError,
          })
        }
      />
      <AlertDialog open={declineOpen} onOpenChange={(next) => !decline.isPending && setDeclineOpen(next)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Decline this request?</AlertDialogTitle>
            <AlertDialogDescription>
              The work stays locked. The creator sees your reason on the post.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <Textarea
            aria-label="Reason (optional)"
            rows={3}
            maxLength={4000}
            placeholder="Reason (optional)"
            disabled={decline.isPending}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
          <AlertDialogFooter>
            <AlertDialogCancel disabled={decline.isPending}>Cancel</AlertDialogCancel>
            <Button
              variant="destructive"
              disabled={decline.isPending}
              pending={decline.isPending}
              onClick={() =>
                decline.mutate(
                  { id: request.id, comment: reason.trim() },
                  {
                    onSuccess: () => {
                      toast.success("Request declined");
                      setDeclineOpen(false);
                    },
                    onError,
                  },
                )
              }
            >
              {decline.isPending ? "Declining…" : "Decline request"}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

/** Where a creator's request stands, on the post: who asked what, and what happens next. */
export function ChangeRequestNotice({ request }: { request?: ChangeRequest | null }) {
  const canReview = useCan()("approval.manage");
  if (!request) return null;
  const who = request.requested_by?.name ?? request.requested_by?.email ?? "A creator";
  const declined = request.status === "declined";
  return (
    <Alert className="mb-6">
      <MessageSquareWarningIcon />
      <AlertTitle>
        {declined
          ? `Change request declined${request.decided_by ? ` by ${request.decided_by.name ?? request.decided_by.email}` : ""}`
          : `${who} requested a ${SCOPE_NAME[request.scope]} change`}
        , {timeAgo(request.decided_at ?? request.created_at)}
      </AlertTitle>
      <AlertDescription className="grid gap-2">
        <p className="whitespace-pre-wrap rounded-md bg-background/60 px-3 py-2 text-sm text-foreground">{request.note}</p>
        {declined ? (
          <span>
            {request.decision_note ? `Reason: ${request.decision_note}. ` : ""}
            The work stays locked.
          </span>
        ) : canReview ? (
          <ChangeRequestActions request={request} />
        ) : (
          <span>Waiting for an admin to decide. The work stays locked until then.</span>
        )}
      </AlertDescription>
    </Alert>
  );
}
