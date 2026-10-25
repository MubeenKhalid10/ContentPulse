"use client";

import { AlertTriangleIcon, CheckIcon, DownloadIcon, FlagIcon, MessageSquarePlusIcon, PaletteIcon, RefreshCwIcon, RotateCcwIcon, XIcon } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { APPROVAL_STATUS_TONE } from "@/lib/tones";
import { BackLink, useFromHere } from "@/components/shared/back-link";
import { AssignDesignerDialog } from "@/components/approvals/assign-designer-dialog";
import { PostProgress } from "@/components/shared/post-progress";
import { SignedImage } from "@/components/shared/signed-image";
import { PlatformTag, Tag } from "@/components/shared/tag";
import { ConfirmDialog } from "@/components/content/confirm-dialog";
import { ArticlePreview } from "@/components/content/article-preview";
import { SocialPostPreview } from "@/components/content/social-preview";
import { SharePostButton } from "@/components/content/share-post-button";
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
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import {
  useAddComment,
  useApproval,
  useApprove,
  useFinalize,
  useReject,
  useReopen,
  useRequestChanges,
} from "@/hooks/use-approvals";
import { api, ApiError, errorMessage } from "@/lib/api";
import { approvalStatusLabel, COMMENT_KIND_LABEL } from "@/lib/approvals";
import { useCan } from "@/lib/auth";
import { POST_STATUS_LABEL, fullText } from "@/lib/content";
import { cleanNote, formatDateTime, timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { ApprovalDetail, ApprovalPage } from "@/types/api";

export function ReviewPage({ id }: { id: string }) {
  const approval = useApproval(id);
  const back = <BackLink href="/approvals" label="Approvals" />;
  if (approval.isError) {
    const notFound = approval.error instanceof ApiError && approval.error.status === 404;
    return (
      <>
        {back}
        <Alert variant="destructive">
          <AlertDescription className="grid gap-2">
            <span>{notFound ? "This submission doesn't exist or isn't in your organization." : errorMessage(approval.error)}</span>
            {!notFound && (
              <Button size="sm" variant="outline" className="w-fit" onClick={() => approval.refetch()}>
                <RefreshCwIcon />
                Retry
              </Button>
            )}
          </AlertDescription>
        </Alert>
      </>
    );
  }
  if (!approval.data) {
    return (
      <>
        {back}
        <Skeleton className="h-10 w-2/3" />
        <div className="mt-6 grid gap-6 lg:grid-cols-3">
          <Skeleton className="h-[32rem] lg:col-span-2" />
          <Skeleton className="h-72" />
        </div>
      </>
    );
  }
  const a = approval.data;

  return (
    <>
      {back}
      <div className="mb-6 grid gap-1.5">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-2xl font-semibold tracking-tight">{a.post.title ?? "Untitled post"}</h1>
          <PlatformTag platform={a.post.platform} />
          <Tag tone={APPROVAL_STATUS_TONE[a.status]} dot>{approvalStatusLabel(a.status, a.stage)}</Tag>
          {a.round > 1 && <Tag tone="orange">Round {a.round}</Tag>}
          {a.post.status === "final" && (
            <div className="ml-auto">
              <SharePostButton title={a.post.title} platform={a.post.platform} copy={a.content} creative={a.creative} />
            </div>
          )}
        </div>
        <p className="text-sm text-muted-foreground">
          Submitted by{" "}
          {a.submitted_by?.name ?? a.submitted_by?.email ?? "someone"}{" "}
          <time title={formatDateTime(a.created_at)}>{timeAgo(a.created_at)}</time> · Post: {POST_STATUS_LABEL[a.post.status]}
        </p>
      </div>

      <PostProgress status={a.post.status} />

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="grid min-w-0 grid-cols-1 content-start gap-6 lg:col-span-2">
          <PreviewCard approval={a} />
        </div>

        <div className="grid min-w-0 grid-cols-1 content-start gap-6">
          <DecisionCard approval={a} />
          <CommentsCard approval={a} />
        </div>
      </div>
    </>
  );
}

/** Copy and design in one frame, the way the platform will show them. */
function PreviewCard({ approval: a }: { approval: ApprovalDetail }) {
  const files = a.creative?.files ?? [];
  const text = a.content ? fullText(a.content.hook, a.content.body, a.content.cta, a.content.hashtags) : "";
  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-start gap-2">
        <div className="grid flex-1 gap-1">
          <CardTitle>How it will look</CardTitle>
          {a.creative?.note && <CardDescription>“{cleanNote(a.creative.note)}”</CardDescription>}
        </div>
      </CardHeader>
      <CardContent className="grid min-w-0 gap-4">
        {a.copy_changed_since && (
          <Alert variant="destructive">
            <AlertTriangleIcon />
            <AlertDescription>
              The copy has changed since this submission (now version {a.post.current_version}). Check that the design still matches.
            </AlertDescription>
          </Alert>
        )}
        {a.post.platform === "blog" ? (
          <div className="mx-auto grid w-full max-w-2xl gap-3">
            {files[0]?.file_type.startsWith("image/") && (
              // Signed, short-lived URLs: next/image can't optimize them.
              <SignedImage src={files[0].url} alt="Featured image" className="aspect-[1.91/1] w-full rounded-xl border object-cover" />
            )}
            {a.content && (
              <ArticlePreview
                title={a.post.title}
                seo={a.content.meta.blog}
                intro={a.content.hook}
                body={a.content.body}
                cta={a.content.cta}
              />
            )}
          </div>
        ) : (
          <SocialPostPreview platform={a.post.platform} text={text} files={files} />
        )}
        {(a.content?.meta.warnings?.length ?? 0) > 0 && (
          <ul className="grid gap-1.5 text-sm text-amber-700 dark:text-amber-400" aria-label="Brand and platform checks">
            {a.content!.meta.warnings!.map((w) => (
              <li key={w} className="flex items-start gap-1.5">
                <AlertTriangleIcon className="mt-0.5 size-4 shrink-0" aria-hidden />
                <span>{w}</span>
              </li>
            ))}
          </ul>
        )}
        {files.length > 0 && (
          <p className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
            Design files:
            {files.map((f) => (
              <a key={f.id} href={f.download_url} className="inline-flex max-w-56 items-center gap-1 underline-offset-4 hover:underline">
                <DownloadIcon className="size-3 shrink-0" />
                <span className="truncate">{f.file_name}</span>
              </a>
            ))}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

const COPY_REOPENABLE = ["design_pending", "design_in_progress", "design_uploaded"];

/** Approved work an admin can still reopen: copy while its design isn't
 * submitted, or a post approved at the final stage. */
function reopenable(a: ApprovalDetail) {
  if (a.status !== "approved") return false;
  return a.stage === "copy"
    ? COPY_REOPENABLE.includes(a.post.status)
    : a.post.status === "final" || a.post.status === "approved";
}

type Scope = "copy" | "design" | "both";
const SCOPES: { value: Scope; label: string; help: string }[] = [
  { value: "copy", label: "Copy", help: "The writer edits the text. The design stays as it is." },
  { value: "design", label: "Design", help: "The designer revises. The copy stays locked." },
  { value: "both", label: "Both", help: "The text and the design both reopen." },
];

/** Request changes: on a pending submission, or (reopen) on approved work. */
function ChangesDialog({
  approval: a,
  open,
  onOpenChange,
}: {
  approval: ApprovalDetail;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const changes = useRequestChanges();
  const reopen = useReopen();
  const [note, setNote] = useState("");
  const [scope, setScope] = useState<Scope>("both");
  const approved = a.status === "approved";
  const mutation = approved ? reopen : changes;
  const copyStage = a.stage === "copy";
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>What should change?</AlertDialogTitle>
          <AlertDialogDescription>
            {copyStage
              ? approved
                ? "The approved copy goes back to its writer. Its design task is cancelled until the copy is approved again."
                : "The post goes back to its writer to revise the copy, then they submit it again."
              : "Only what you choose opens for editing. Everything else stays locked."}
          </AlertDialogDescription>
        </AlertDialogHeader>
        {!copyStage && (
          <div role="radiogroup" aria-label="What needs changes" className="grid gap-1.5">
            {SCOPES.map((option) => (
              <button
                key={option.value}
                type="button"
                role="radio"
                aria-checked={scope === option.value}
                tabIndex={scope === option.value ? 0 : -1}
                onClick={() => setScope(option.value)}
                onKeyDown={(e) => {
                  const i = SCOPES.findIndex((o) => o.value === scope);
                  if (e.key === "ArrowRight" || e.key === "ArrowDown") {
                    e.preventDefault();
                    setScope(SCOPES[(i + 1) % SCOPES.length].value);
                  } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
                    e.preventDefault();
                    setScope(SCOPES[(i + SCOPES.length - 1) % SCOPES.length].value);
                  }
                }}
                className={cn(
                  "grid rounded-lg border px-3 py-2 text-left text-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
                  scope === option.value ? "border-primary bg-primary/5" : "hover:bg-muted",
                )}
              >
                <span className="font-medium">{option.label}</span>
                <span className="text-xs text-muted-foreground">{option.help}</span>
              </button>
            ))}
          </div>
        )}
        <Textarea
          aria-label="What should change"
          rows={4}
          maxLength={4000}
          placeholder="e.g. Shorten the headline and use the brand blue on slide 3."
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
        <p className="-mt-2 text-right text-xs tabular-nums text-muted-foreground">{note.length} / 4000</p>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={mutation.isPending}>Cancel</AlertDialogCancel>
          {/* A plain button: the dialog stays open if the request fails. */}
          <Button
            disabled={!note.trim() || mutation.isPending}
            onClick={() =>
              mutation.mutate(
                { id: a.id, comment: note.trim(), scope: copyStage ? "both" : scope },
                {
                  onSuccess: () => {
                    toast.success("Changes requested");
                    setNote("");
                    onOpenChange(false);
                  },
                  onError: (e: unknown) => toast.error(errorMessage(e)),
                },
              )
            }
          >
            {mutation.isPending ? "Sending…" : "Request changes"}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

function DecisionCard({ approval: a }: { approval: ApprovalDetail }) {
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
        <Button disabled={busy} onClick={() => setApproveOpen(true)}>
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

function CommentsCard({ approval: a }: { approval: ApprovalDetail }) {
  const can = useCan();
  const canComment = can("approval.manage") || can("content.edit");
  const add = useAddComment();
  const [body, setBody] = useState("");
  return (
    <Card>
      <CardHeader>
        <CardTitle>Comments</CardTitle>
        <CardDescription>Every round of this post. Each comment shows the versions it refers to.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        {a.comments.length === 0 ? (
          <p className="text-sm text-muted-foreground">No comments yet.</p>
        ) : (
          <ol className="grid gap-3" aria-label="Comments">
            {a.comments.map((c) => (
              <li key={c.id} className={cn("grid gap-1 rounded-lg p-3 text-sm", c.approval_request_id === a.id ? "bg-muted/60" : "bg-muted/30")}>
                <span className="flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
                  <span className="font-medium text-foreground">{c.author?.name ?? c.author?.email ?? "Someone"}</span>
                  {COMMENT_KIND_LABEL[c.kind]}
                  {c.approval_request_id !== a.id && <Tag tone="neutral">Previous round</Tag>}
                  <time className="ml-auto" title={formatDateTime(c.created_at)}>
                    {timeAgo(c.created_at)}
                  </time>
                </span>
                <p className="whitespace-pre-wrap">{c.body}</p>
              </li>
            ))}
          </ol>
        )}
        {canComment && (
          <form
            className="grid gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (!body.trim()) return;
              add.mutate(
                { id: a.id, body: body.trim() },
                { onSuccess: () => setBody(""), onError: (err) => toast.error(errorMessage(err)) },
              );
            }}
          >
            <Textarea aria-label="Add a comment" rows={2} maxLength={4000} placeholder="Add a comment" value={body} onChange={(e) => setBody(e.target.value)} />
            <p className="text-right text-xs tabular-nums text-muted-foreground">{body.length} / 4000</p>
            <Button type="submit" size="sm" variant="outline" className="justify-self-end" disabled={!body.trim() || add.isPending}>
              <MessageSquarePlusIcon />
              {add.isPending ? "Posting…" : "Comment"}
            </Button>
          </form>
        )}
      </CardContent>
    </Card>
  );
}

