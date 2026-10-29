"use client";

import {
  AlertTriangleIcon,
  CheckIcon,
  FlagIcon,
  PaletteIcon,
  RotateCcwIcon,
  XIcon,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { useFromHere } from "@/components/shared/back-link";
import { AssignDesignerDialog } from "@/components/approvals/assign-designer-dialog";
import { ConfirmDialog } from "@/components/content/confirm-dialog";
import { HandoffButtons } from "@/components/design/handoff-buttons";
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
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { useApprove, useFinalize, useReject } from "@/hooks/use-approvals";
import { api, errorMessage } from "@/lib/api";
import { approvalStatusLabel } from "@/lib/approvals";
import { useCan } from "@/lib/auth";
import { formatDateTime, timeAgo } from "@/lib/format";
import type { ApprovalDetail, ApprovalPage } from "@/types/api";

import { ChangesDialog } from "./changes-dialog";

const COPY_REOPENABLE = ["design_pending", "design_in_progress", "design_uploaded"];

/** Approved work an admin can still reopen: copy while its design isn't
 * submitted, or a post approved at the final stage. */
function reopenable(a: ApprovalDetail) {
  if (a.status !== "approved") return false;
  return a.stage === "copy"
    ? COPY_REOPENABLE.includes(a.post.status)
    : a.post.status === "final" || a.post.status === "approved";
}

export function DecisionCard({ approval: a }: { approval: ApprovalDetail }) {
  const fromHere = useFromHere();
  const can = useCan()("approval.manage");
  const approve = useApprove();
  const reject = useReject();
  const finalize = useFinalize();
  // Each decision has its own comment, so text never goes out with the wrong button.
  const [changesOpen, setChangesOpen] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectNote, setRejectNote] = useState("");
  const [approveOpen, setApproveOpen] = useState(false);
  // Set after the content is approved: the admin picks who designs the post.
  const [assignTaskId, setAssignTaskId] = useState<string | null>(null);
  const router = useRouter();
  const busy = approve.isPending || reject.isPending;
  const onError = (e: unknown) => toast.error(errorMessage(e));
  // After approving, stay in Approvals: the next submission waiting at this
  // stage, or the list when there is none.
  const openNext = async () => {
    const waiting = await api<ApprovalPage>(
      `/approvals?stage=${a.stage}&status=pending&limit=2`,
    ).catch(() => null);
    const next = waiting?.items.find((i) => i.id !== a.id);
    router.push(next ? `/approvals/${next.id}` : "/approvals");
  };

  // Kept outside the branches below: approving refreshes the approval, which switches branch.
  const assignDialog = (
    <AssignDesignerDialog
      taskId={assignTaskId}
      open={!!assignTaskId}
      onDone={() => {
        setAssignTaskId(null);
        void openNext();
      }}
    />
  );

  if (a.status !== "pending") {
    return (
      <Card>
        {assignDialog}
        <CardHeader>
          <CardTitle>
            {a.stage === "copy" && a.status === "approved"
              ? "Copy approved: ready for design"
              : a.post.status === "final" && a.status === "approved"
                ? "Ready to publish"
                : approvalStatusLabel(a.status, a.stage)}
          </CardTitle>
          <CardDescription>
            {a.reviewer && `${a.status === "approved" ? "Approved" : "Decided"} by ${a.reviewer.name ?? a.reviewer.email}`}
            {a.reviewed_at && <> · <time title={formatDateTime(a.reviewed_at)}>{timeAgo(a.reviewed_at)}</time></>}
          </CardDescription>
        </CardHeader>
        {/* Copy approved: the design brief is open, ready to hand to a designer. */}
        {a.stage === "copy" && a.status === "approved" && a.brief && (
          <CardContent className="grid gap-3">
            <p className="text-sm text-muted-foreground">
              The design brief and brand guidelines for this post are ready. Open it to check them, or export the brief and send it
              to your designer.
            </p>
            <Link href={fromHere(`/design/${a.brief.id}`)} className={buttonVariants()}>
              <PaletteIcon />
              Open design brief
            </Link>
            <div className="flex flex-wrap gap-2">
              <HandoffButtons id={a.brief.id} />
            </div>
          </CardContent>
        )}
        {/* Posts approved before approval and finalizing became one step. */}
        {can && a.status === "approved" && a.post.status === "approved" && (
          <CardContent>
            <Button
              className="w-full"
              disabled={finalize.isPending}
              pending={finalize.isPending}
              onClick={() => finalize.mutate(a.id, { onSuccess: () => toast.success("Ready to publish"), onError })}
            >
              <FlagIcon />
              Mark ready to publish
            </Button>
          </CardContent>
        )}
        {a.post.status === "final" && (
          <CardContent className="text-sm text-muted-foreground">Locked and ready to publish. Use Share on the post.</CardContent>
        )}
        {can && reopenable(a) && (
          <CardContent className="grid gap-2">
            <p className="text-sm text-muted-foreground">
              Approved {a.stage === "copy" ? "copy is" : "work is"} locked. Request changes to let the creator edit it again.
            </p>
            <Button variant="outline" onClick={() => setChangesOpen(true)}>
              <RotateCcwIcon />
              Request changes
            </Button>
            <ChangesDialog approval={a} open={changesOpen} onOpenChange={setChangesOpen} />
          </CardContent>
        )}
      </Card>
    );
  }
  if (!can) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{approvalStatusLabel("pending", a.stage)}</CardTitle>
          <CardDescription>
            {a.stage === "copy"
              ? "An admin will approve the copy, which opens the design brief, or ask for changes."
              : "An admin will approve this post or ask for changes."}
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>Your decision</CardTitle>
        <CardDescription>
          {a.stage === "copy"
            ? "Approving the content sends the post to design. You will choose who designs it next. "
            : "The content is already approved, so approving this design also approves the post and makes it Ready to publish. "}
          Checking copy v{a.post_version}
          {a.creative_version != null && ` and design v${a.creative_version}`}.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-2">
        {a.copy_changed_since && (
          <Alert variant="destructive" className="mb-1">
            <AlertTriangleIcon />
            <AlertTitle>The copy changed after this was submitted</AlertTitle>
            <AlertDescription>Review the latest version before you approve.</AlertDescription>
          </Alert>
        )}
        <Button disabled={busy} pending={approve.isPending} onClick={() => setApproveOpen(true)}>
          <CheckIcon />
          {a.stage === "copy" ? "Approve content" : "Approve design and post"}
        </Button>
        <ConfirmDialog
          open={approveOpen}
          onOpenChange={setApproveOpen}
          title={a.stage === "copy" ? "Approve this content?" : "Approve the design and the post?"}
          description={
            a.stage === "copy"
              ? "The copy is locked and the post moves to design. You will choose who designs it next. You can still request changes later."
              : "The design and the post are approved and locked, and the post becomes Ready to publish. You can still request changes later."
          }
          confirmLabel={a.stage === "copy" ? "Approve content" : "Approve design and post"}
          pending={busy}
          onConfirm={() =>
            approve.mutate(
              { id: a.id, comment: "" },
              {
                onSuccess: (res) => {
                  toast.success(
                    a.stage === "copy"
                      ? "Content approved. Its design brief is ready."
                      : "Design and post approved: the post is now Ready to publish.",
                  );
                  if (a.stage === "copy" && res.brief) {
                    setAssignTaskId(res.brief.id);
                    return;
                  }
                  void openNext();
                },
                onError,
              },
            )
          }
        />
        <Button variant="outline" disabled={busy} onClick={() => setChangesOpen(true)}>
          <RotateCcwIcon />
          Request changes
        </Button>
        <Button variant="ghost" className="text-destructive" disabled={busy} onClick={() => setRejectOpen(true)}>
          <XIcon />
          Reject
        </Button>
      </CardContent>

      {assignDialog}

      <ChangesDialog approval={a} open={changesOpen} onOpenChange={setChangesOpen} />

      <AlertDialog open={rejectOpen} onOpenChange={setRejectOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Reject this post?</AlertDialogTitle>
            <AlertDialogDescription>
              The writer will not be able to edit or resubmit. Use Request changes to ask for a revision.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <Textarea
            aria-label="Reason (optional)"
            rows={3}
            maxLength={4000}
            placeholder="Reason (optional)"
            value={rejectNote}
            onChange={(e) => setRejectNote(e.target.value)}
          />
          <AlertDialogFooter>
            <AlertDialogCancel disabled={reject.isPending}>Cancel</AlertDialogCancel>
            <Button
              variant="destructive"
              disabled={busy}
              pending={reject.isPending}
              onClick={() =>
                reject.mutate(
                  { id: a.id, comment: rejectNote.trim() },
                  {
                    onSuccess: () => {
                      toast.success("Post rejected");
                      setRejectNote("");
                      setRejectOpen(false);
                    },
                    onError,
                  },
                )
              }
            >
              {reject.isPending ? "Rejecting…" : "Reject post"}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
}
