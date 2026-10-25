"use client";

import {
  AlertTriangleIcon,
  CopyPlusIcon,
  EllipsisIcon,
  EyeIcon,
  LoaderCircleIcon,
  LockIcon,
  PaletteIcon,
  RefreshCwIcon,
  RotateCcwIcon,
  SendIcon,
  Undo2Icon,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { POST_STATUS_TONE } from "@/lib/tones";
import { BackLink, useFromHere } from "@/components/shared/back-link";
import { PlatformTag, Tag } from "@/components/shared/tag";
import { ReviewBanner } from "@/components/approvals/review-banner";
import { ConfirmDialog } from "@/components/content/confirm-dialog";
import { PostEditor } from "@/components/content/post-editor";
import { SharePostButton } from "@/components/content/share-post-button";
import { DeleteButton } from "@/components/shared/delete-button";
import { PostProgress } from "@/components/shared/post-progress";
import {
  PreviewPanel,
  VariantsPanel,
} from "@/components/content/studio-panels";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useResubmitPost } from "@/hooks/use-approvals";
import { type PostAction, useCreateVariant, useDeletePost, usePost, usePostAction, useRegenerate } from "@/hooks/use-content";
import { ApiError, errorMessage } from "@/lib/api";
import { useCan } from "@/lib/auth";
import { POST_STATUS_LABEL } from "@/lib/content";
import { PLATFORM_LABEL } from "@/lib/topics";
import type { PostDetail } from "@/types/api";

export function ContentStudio({ id }: { id: string }) {
  const fromHere = useFromHere();
  const post = usePost(id);
  const can = useCan();
  const canEdit = can("content.edit");
  const canGenerate = can("content.generate");

  const back = <BackLink href="/content" label="Write posts" />;

  if (post.isError) {
    const notFound = post.error instanceof ApiError && post.error.status === 404;
    return (
      <>
        {back}
        <Alert variant="destructive">
          <AlertDescription className="grid gap-2">
            <span>{notFound ? "This post doesn't exist or isn't in your organization." : errorMessage(post.error)}</span>
            {!notFound && (
              <Button size="sm" variant="outline" className="w-fit" onClick={() => post.refetch()}>
                <RefreshCwIcon />
                Retry
              </Button>
            )}
          </AlertDescription>
        </Alert>
      </>
    );
  }
  if (!post.data) {
    return (
      <>
        {back}
        <Skeleton className="h-10 w-2/3" />
        <div className="mt-6 grid gap-6 lg:grid-cols-3">
          <Skeleton className="h-[32rem] lg:col-span-2" />
          <Skeleton className="h-64" />
        </div>
      </>
    );
  }

  const p = post.data;
  const generating = p.generation?.status === "queued" || p.generation?.status === "running";

  return (
    <>
      {back}
      <div className="mb-6 flex flex-wrap items-start gap-4">
        <div className="grid min-w-0 flex-1 gap-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">{p.title ?? "Untitled post"}</h1>
            <PlatformTag platform={p.platform} />
            <Tag tone={POST_STATUS_TONE[p.status]} dot>{POST_STATUS_LABEL[p.status]}</Tag>
            {p.variant_of_id && <Tag tone="neutral">Variant</Tag>}
          </div>
          <p className="text-sm text-muted-foreground">
            {p.current_version ? `Version ${p.current_version}` : "No version yet"}
            {p.topic && (
              <>
                {" · "}
                <Link href={fromHere(`/topics/${p.topic.id}`)} className="underline-offset-4 hover:underline">
                  {p.topic.title}
                </Link>
              </>
            )}
            {p.design_task && (
              <>
                {" · "}
                <Link href={fromHere(`/design/${p.design_task.id}`)} className="font-medium text-foreground underline-offset-4 hover:underline">
                  Design task
                </Link>
              </>
            )}
          </p>
        </div>
        <StudioActions
          post={p}
          canEdit={canEdit}
          canGenerate={canGenerate}
          canShare={can("content.read")}
          generating={generating}
        />
      </div>

      <PostProgress status={p.status} />

      <GenerationBanner post={p} canGenerate={canGenerate} generating={generating} />
      <LockedNotice post={p} />
      <ReviewBanner review={p.review}>
        {p.status === "changes_requested" && canEdit && <ResubmitControl postId={p.id} />}
      </ReviewBanner>

      {p.current ? (
        <div className="grid gap-6 lg:grid-cols-3">
          <div className="lg:col-span-2">
            {/* Remount on a new version so the form shows what was saved or generated. */}
            <PostEditor key={`${p.id}:${p.current_version}`} post={p} canEdit={canEdit && !generating} />
          </div>
          <div className="grid content-start gap-6">
            <PreviewPanel post={p} />
            <VariantsPanel post={p} />
          </div>
        </div>
      ) : (
        generating && (
          <div className="grid gap-6 lg:grid-cols-3" aria-hidden>
            <Skeleton className="h-[28rem] lg:col-span-2" />
            <Skeleton className="h-48" />
          </div>
        )
      )}
    </>
  );
}

// Statuses after the copy was approved, where it's locked unless reopened.
const APPROVED_COPY = [
  "design_pending",
  "design_in_progress",
  "design_uploaded",
  "pending_approval",
  "changes_requested",
  "approved",
  "final",
];

/** Approved copy is read-only until an admin requests changes to it. */
function LockedNotice({ post }: { post: PostDetail }) {
  const fromHere = useFromHere();
  const canReview = useCan()("approval.manage");
  if (!post.editable && post.status === "content_review") {
    return (
      <Alert className="mb-6">
        <LockIcon />
        <AlertTitle>With an admin for approval</AlertTitle>
        <AlertDescription>
          The copy is locked while an admin reviews it. To change it, withdraw it from review (the ⋯ More actions
          menu at the top) and send it again when you are done.
        </AlertDescription>
      </Alert>
    );
  }
  if (post.editable || !APPROVED_COPY.includes(post.status)) return null;
  const reopenHref = post.review?.status === "approved" ? `/approvals/${post.review.request_id}` : null;
  return (
    <Alert className="mb-6">
      <LockIcon />
      <AlertTitle>Approved copy is locked</AlertTitle>
      <AlertDescription className="grid gap-2">
        <span>
          {post.status === "changes_requested"
            ? "The admin asked for design changes only, so the copy stays as approved."
            : canReview
              ? "Request changes to let the creator edit it again."
              : "An admin can request changes to reopen it."}
        </span>
        {canReview && reopenHref && (
          <Link href={fromHere(reopenHref)} className={buttonVariants({ size: "sm", variant: "outline" }) + " w-fit"}>
            <RotateCcwIcon />
            Request changes
          </Link>
        )}
      </AlertDescription>
    </Alert>
  );
}

function ResubmitControl({ postId }: { postId: string }) {
  const resubmit = useResubmitPost();
  const [note, setNote] = useState("");
  const [confirmOpen, setConfirmOpen] = useState(false);
  return (
    <form
      className="flex flex-wrap items-center gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        setConfirmOpen(true);
      }}
    >
      <Input
        aria-label="Note for the reviewer"
        placeholder="What did you change? (optional)"
        value={note}
        onChange={(e) => setNote(e.target.value)}
        className="min-w-48 flex-1 bg-background"
      />
      <Button type="submit" size="sm" disabled={resubmit.isPending}>
        <SendIcon />
        {resubmit.isPending ? "Resubmitting…" : "Resubmit for approval"}
      </Button>
      <span className="w-full text-xs text-muted-foreground">
        Save your edits first: unsaved changes are not sent. Fixed the copy? Resubmit with the current design. Need
        a new design? Use “Update design” at the top.
      </span>
      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Resubmit for approval?"
        description="The admin is notified and will review your saved copy with the current design again. Unsaved edits are not included."
        confirmLabel="Resubmit"
        pending={resubmit.isPending}
        onConfirm={() =>
          resubmit.mutate(
            { id: postId, note: note.trim() },
            { onSuccess: () => toast.success("Resubmitted for approval"), onError: (err) => toast.error(errorMessage(err)) },
          )
        }
      />
    </form>
  );
}

function GenerationBanner({ post, canGenerate, generating }: { post: PostDetail; canGenerate: boolean; generating: boolean }) {
  const regenerate = useRegenerate();
  const remove = useDeletePost();
  const canEdit = useCan()("content.edit");
  const router = useRouter();
  const g = post.generation;
  if (!g) return null;
  if (generating) {
    return (
      <Alert className="mb-6" role="status">
        <LoaderCircleIcon className="animate-spin" />
        <AlertTitle>
          {g.kind === "regenerate" ? "Rewriting" : "Writing"} your {PLATFORM_LABEL[post.platform]} post…
        </AlertTitle>
        <AlertDescription>
          {g.engine === "ai"
            ? "Using your plan, brand rules, playbook and knowledge base. This page updates by itself when the draft is ready."
            : "Building a template draft from your plan (AI writing isn't switched on)."}
        </AlertDescription>
      </Alert>
    );
  }
  if (g.status === "failed") {
    return (
      <Alert variant="destructive" className="mb-6">
        <AlertTriangleIcon />
        <AlertTitle>{post.current ? "The last regeneration failed" : "Generation failed"}</AlertTitle>
        <AlertDescription className="grid gap-2">
          <span>
            {g.error}
            {post.current && " Your saved versions are unchanged."}
          </span>
          <div className="flex flex-wrap gap-2">
            {canGenerate && post.editable && (
              <Button
                size="sm"
                variant="outline"
                disabled={regenerate.isPending || remove.isPending}
                onClick={() => regenerate.mutate({ id: post.id }, { onError: (e) => toast.error(errorMessage(e)) })}
              >
                <RefreshCwIcon />
                Try again
              </Button>
            )}
            {/* Nothing written yet: the post can go, without touching the others. */}
            {canEdit && !post.current && post.status === "draft" && (
              <DeleteButton
                label="Delete post"
                title="Delete this failed post?"
                description="Nothing was written, so only this empty post is removed. Your plan and other posts are not affected. This can't be undone."
                pending={regenerate.isPending || remove.isPending}
                onConfirm={() =>
                  remove.mutate(post.id, {
                    onSuccess: () => {
                      toast.success("Failed post deleted");
                      router.push("/content");
                    },
                    onError: (e) => toast.error(errorMessage(e)),
                  })
                }
              />
            )}
          </div>
        </AlertDescription>
      </Alert>
    );
  }
  if (g.status === "succeeded" && g.engine === "template" && post.current?.meta.engine === "template") {
    return (
      <Alert className="mb-6">
        <AlertTitle>Template draft</AlertTitle>
        <AlertDescription>
          AI writing isn&apos;t switched on, so this draft restates your plan for you to finish. Ask your admin to set up
          an AI model for AI-written copy.
        </AlertDescription>
      </Alert>
    );
  }
  return null;
}

const ACTION_COPY: Record<PostAction, string> = {
  "back-to-draft": "Moved back to draft",
  "submit-for-review": "Sent to an admin for approval",
  archive: "Post archived",
};
// The post's design task is where the creative is uploaded and submitted.
const DESIGN_STEP = ["design_pending", "design_in_progress", "design_uploaded", "changes_requested"];

function StudioActions({
  post,
  canEdit,
  canGenerate,
  canShare,
  generating,
}: {
  post: PostDetail;
  canEdit: boolean;
  canGenerate: boolean;
  canShare: boolean;
  generating: boolean;
}) {
  const fromHere = useFromHere();
  const router = useRouter();
  const canReview = useCan()("approval.manage");
  const isAdmin = useCan()("organization.write");
  const removePost = useDeletePost();
  const action = usePostAction();
  const variant = useCreateVariant();
  const [regenOpen, setRegenOpen] = useState(false);
  const [confirm, setConfirm] = useState<"submit" | "back" | null>(null);
  const onError = (e: unknown) => toast.error(errorMessage(e));
  const run = (kind: PostAction) =>
    action.mutate({ id: post.id, action: kind }, { onSuccess: () => toast.success(ACTION_COPY[kind]), onError });
  const busy = action.isPending || generating;
  const hasCopy = post.current_version > 0;
  const s = post.status;
  const canVariant = canGenerate && post.editable && !!post.content_strategy_id;
  // Withdrawing from review is the writer's call; taking a post back from
  // design reopens approved copy, so only an admin can.
  const canBackToDraft =
    (canEdit && s === "content_review") ||
    (canReview && ["design_pending", "design_in_progress", "design_uploaded"].includes(s));
  const hasMore = canVariant || canBackToDraft;

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {canShare && s === "final" && (
        <SharePostButton
          title={post.title}
          platform={post.platform}
          copy={post.current}
          creative={
            post.review?.creative_version
              ? post.creatives.find((creative) => creative.version === post.review?.creative_version) ?? null
              : post.creatives[0] ?? null
          }
        />
      )}
      {canGenerate && post.editable && (
        <Button variant="outline" size="sm" disabled={busy} onClick={() => setRegenOpen(true)}>
          <RefreshCwIcon />
          Rewrite with AI
        </Button>
      )}
      {canEdit && s === "draft" && (
        <Button size="sm" disabled={busy || !hasCopy} onClick={() => setConfirm("submit")}>
          <SendIcon />
          Submit for approval
        </Button>
      )}
      {canEdit && s === "draft" && !hasCopy && (
        <span className="w-full text-right text-xs text-muted-foreground">Write the copy first to submit it for approval.</span>
      )}
      {s === "content_review" && canReview && post.review && (
        <Link href={fromHere(`/approvals/${post.review.request_id}`)} className={buttonVariants({ size: "sm" })}>
          <EyeIcon />
          Review
        </Link>
      )}
      {DESIGN_STEP.includes(s) && post.design_task && (
        <Link href={fromHere(`/design/${post.design_task.id}`)} className={buttonVariants({ size: "sm" })}>
          <PaletteIcon />
          {s === "changes_requested" ? "Update design" : s === "design_pending" ? "Add design" : "Continue design"}
        </Link>
      )}
      {hasMore && (
        <DropdownMenu>
          <DropdownMenuTrigger
            aria-label="More actions"
            className={buttonVariants({ variant: "ghost", size: "icon-sm" })}
            disabled={busy}
          >
            <EllipsisIcon />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-52">
            {canVariant && (
              <DropdownMenuItem
                onClick={() =>
                  variant.mutate(post.id, {
                    onSuccess: (v) => {
                      toast.success("Writing another version as a separate post…");
                      router.push(`/content/${v.id}`);
                    },
                    onError,
                  })
                }
              >
                <CopyPlusIcon />
                Write another version
              </DropdownMenuItem>
            )}
            {canBackToDraft && (
              <DropdownMenuItem onClick={() => setConfirm("back")}>
                <Undo2Icon />
                {s === "content_review" ? "Withdraw from review" : "Reopen copy"}
              </DropdownMenuItem>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      )}
      {isAdmin && <span className="mx-1 hidden h-5 w-px bg-border sm:block" aria-hidden />}
      {isAdmin && (
        <DeleteButton
          title={`Delete “${post.title ?? "this post"}”?`}
          description="This permanently deletes the post and everything attached to it: every version of the copy, its design task and files, and its approvals. The plan it came from is kept. This can't be undone."
          pending={removePost.isPending || generating}
          onConfirm={() =>
            removePost.mutate(post.id, {
              onSuccess: () => {
                toast.success("Post deleted");
                router.push("/content");
              },
              onError,
            })
          }
        />
      )}
      <ConfirmDialog
        open={confirm === "submit"}
        onOpenChange={(o) => !o && setConfirm(null)}
        title="Submit for approval?"
        description="An admin will review this copy. While it is in review the copy is locked; you can withdraw it from review if you need to edit."
        confirmLabel="Submit"
        pending={action.isPending}
        onConfirm={() => run("submit-for-review")}
      />
      <ConfirmDialog
        open={confirm === "back"}
        onOpenChange={(o) => !o && setConfirm(null)}
        title={s === "content_review" ? "Withdraw from review?" : "Reopen the copy?"}
        description={
          s === "content_review"
            ? "The admin's review is cancelled and the post goes back to draft so you can edit it. Submit it again when you are done."
            : "The approved copy becomes editable again and the post goes back to draft. It will need content approval again."
        }
        confirmLabel={s === "content_review" ? "Withdraw" : "Reopen copy"}
        pending={action.isPending}
        onConfirm={() => run("back-to-draft")}
      />
      <RegenerateDialog post={post} open={regenOpen} onClose={() => setRegenOpen(false)} />
    </div>
  );
}

function RegenerateDialog({ post, open, onClose }: { post: PostDetail; open: boolean; onClose: () => void }) {
  const regenerate = useRegenerate();
  const [instructions, setInstructions] = useState("");
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (next || regenerate.isPending) return;
        setInstructions("");
        onClose();
      }}
    >
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Rewrite with AI</DialogTitle>
          <DialogDescription>
            Writes a new version from the same plan. The current version stays in the history. Edits you have not saved in the editor will be lost.
          </DialogDescription>
        </DialogHeader>
        <label htmlFor="regen-instructions" className="grid gap-1.5 text-sm font-medium">
          Instructions (optional)
          <Textarea
            id="regen-instructions"
            rows={3}
            maxLength={1000}
            placeholder="e.g. Shorter, and lead with the statistic"
            value={instructions}
            onChange={(e) => setInstructions(e.target.value)}
          />
        </label>
        <DialogFooter>
          <Button
            variant="outline"
            disabled={regenerate.isPending}
            onClick={() => {
              setInstructions("");
              onClose();
            }}
          >
            Cancel
          </Button>
          <Button
            disabled={regenerate.isPending}
            onClick={() =>
              regenerate.mutate(
                { id: post.id, instructions: instructions.trim() || undefined },
                {
                  onSuccess: () => {
                    setInstructions("");
                    toast.success("Rewriting your post…");
                    onClose();
                  },
                  onError: (e) => toast.error(errorMessage(e)),
                },
              )
            }
          >
            <RefreshCwIcon />
            {regenerate.isPending ? "Starting…" : "Rewrite"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
