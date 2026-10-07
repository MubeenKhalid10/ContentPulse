"use client";

import {
  AlertTriangleIcon,
  ArchiveIcon,
  ArrowLeftIcon,
  CopyPlusIcon,
  EllipsisIcon,
  LoaderCircleIcon,
  PaletteIcon,
  RefreshCwIcon,
  SendIcon,
  Undo2Icon,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { POST_STATUS_TONE } from "@/lib/tones";
import { PlatformTag, Tag } from "@/components/shared/tag";
import { ReviewBanner } from "@/components/approvals/review-banner";
import { PostEditor } from "@/components/content/post-editor";
import { SharePostButton } from "@/components/content/share-post-button";
import {
  ChecksPanel,
  PreviewPanel,
  SourcesPanel,
  StrategyPanel,
  VariantsPanel,
  VersionsPanel,
} from "@/components/content/studio-panels";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
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
import { Textarea } from "@/components/ui/textarea";
import { useResubmitPost } from "@/hooks/use-approvals";
import { type PostAction, useCreateVariant, usePost, usePostAction, useRegenerate } from "@/hooks/use-content";
import { ApiError, errorMessage } from "@/lib/api";
import { useCan } from "@/lib/auth";
import { POST_STATUS_LABEL } from "@/lib/content";
import { PLATFORM_LABEL } from "@/lib/topics";
import type { PostDetail } from "@/types/api";

export function ContentStudio({ id }: { id: string }) {
  const post = usePost(id);
  const can = useCan();
  const canEdit = can("content.edit");
  const canGenerate = can("content.generate");

  const back = (
    <Link href="/content" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
      <ArrowLeftIcon className="size-4" />
      Content studio
    </Link>
  );

  if (post.isError) {
    const notFound = post.error instanceof ApiError && post.error.status === 404;
    return (
      <>
        {back}
        <Alert variant="destructive">
          <AlertDescription>{notFound ? "This post doesn't exist or isn't in your organization." : errorMessage(post.error)}</AlertDescription>
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
                <Link href={`/topics/${p.topic.id}`} className="underline-offset-4 hover:underline">
                  {p.topic.title}
                </Link>
              </>
            )}
            {p.design_task && (
              <>
                {" · "}
                <Link href={`/design/${p.design_task.id}`} className="font-medium text-foreground underline-offset-4 hover:underline">
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

      <GenerationBanner post={p} canGenerate={canGenerate} generating={generating} />
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
            <ChecksPanel post={p} />
            <PreviewPanel post={p} />
            <VersionsPanel post={p} canEdit={canEdit} />
            <VariantsPanel post={p} />
            <SourcesPanel post={p} />
            <StrategyPanel post={p} />
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

function ResubmitControl({ postId }: { postId: string }) {
  const resubmit = useResubmitPost();
  const [note, setNote] = useState("");
  return (
    <form
      className="flex flex-wrap items-center gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        resubmit.mutate(
          { id: postId, note: note.trim() },
          { onSuccess: () => toast.success("Resubmitted for approval"), onError: (err) => toast.error(errorMessage(err)) },
        );
      }}
    >
      <input
        aria-label="Note for the reviewer"
        placeholder="What did you change? (optional)"
        value={note}
        onChange={(e) => setNote(e.target.value)}
        className="h-8 min-w-48 flex-1 rounded-lg border border-input bg-background px-2.5 text-sm"
      />
      <Button type="submit" size="sm" disabled={resubmit.isPending}>
        <SendIcon />
        Resubmit for approval
      </Button>
      <span className="w-full text-xs text-muted-foreground">
        Fixed the copy? Save it, then resubmit with the current design. Need a new design? Use “Update design &
        resubmit” at the top.
      </span>
    </form>
  );
}

function GenerationBanner({ post, canGenerate, generating }: { post: PostDetail; canGenerate: boolean; generating: boolean }) {
  const regenerate = useRegenerate();
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
            ? "Using your plan, brand rules, playbook and knowledge base. This usually takes under a minute."
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
          {canGenerate && post.editable && (
            <Button
              size="sm"
              variant="outline"
              className="justify-self-start"
              disabled={regenerate.isPending}
              onClick={() => regenerate.mutate({ id: post.id }, { onError: (e) => toast.error(errorMessage(e)) })}
            >
              <RefreshCwIcon />
              Try again
            </Button>
          )}
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
  "send-to-design": "Sent to design",
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
  const router = useRouter();
  const action = usePostAction();
  const variant = useCreateVariant();
  const [regenOpen, setRegenOpen] = useState(false);
  const [confirmArchive, setConfirmArchive] = useState(false);
  const onError = (e: unknown) => toast.error(errorMessage(e));
  const run = (kind: PostAction) =>
    action.mutate({ id: post.id, action: kind }, { onSuccess: () => toast.success(ACTION_COPY[kind]), onError });
  const busy = action.isPending || generating;
  const hasCopy = post.current_version > 0;
  const s = post.status;
  const canVariant = canGenerate && post.editable && !!post.content_strategy_id;
  // A post waiting for a decision can't be archived; withdraw nothing mid-review.
  const canArchive = canEdit && s !== "archived" && s !== "pending_approval";
  const canBackToDraft = canEdit && s === "design_pending";
  const hasMore = canVariant || canArchive || canBackToDraft;

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
      {canEdit && (s === "draft" || s === "content_review") && (
        <Button
          size="sm"
          disabled={busy || !hasCopy}
          onClick={() =>
            action.mutate(
              { id: post.id, action: "send-to-design" },
              {
                // Straight to the design task: upload the creative there and submit.
                onSuccess: (sent) => {
                  toast.success("Sent to design. Add the creative next.");
                  if (sent.design_task) router.push(`/design/${sent.design_task.id}`);
                },
                onError,
              },
            )
          }
        >
          <PaletteIcon />
          Send to design
        </Button>
      )}
      {DESIGN_STEP.includes(s) && post.design_task && (
        <Link href={`/design/${post.design_task.id}`} className={buttonVariants({ size: "sm" })}>
          <PaletteIcon />
          {s === "changes_requested" ? "Update design & resubmit" : "Add design & submit"}
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
              <DropdownMenuItem onClick={() => run("back-to-draft")}>
                <Undo2Icon />
                Take back from design
              </DropdownMenuItem>
            )}
            {canArchive && (
              <DropdownMenuItem variant="destructive" onClick={() => setConfirmArchive(true)}>
                <ArchiveIcon />
                Archive post
              </DropdownMenuItem>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      )}
      <RegenerateDialog post={post} open={regenOpen} onClose={() => setRegenOpen(false)} />
      <AlertDialog open={confirmArchive} onOpenChange={setConfirmArchive}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Archive this post?</AlertDialogTitle>
            <AlertDialogDescription>
              It leaves the workflow but stays in the Archived tab with all its versions.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                run("archive");
                setConfirmArchive(false);
              }}
            >
              Archive
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function RegenerateDialog({ post, open, onClose }: { post: PostDetail; open: boolean; onClose: () => void }) {
  const regenerate = useRegenerate();
  const [instructions, setInstructions] = useState("");
  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Rewrite with AI</DialogTitle>
          <DialogDescription>
            Writes a new version from the same plan. The current version stays in the history.
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
          <Button variant="outline" onClick={onClose}>
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
                    onClose();
                  },
                  onError: (e) => toast.error(errorMessage(e)),
                },
              )
            }
          >
            <RefreshCwIcon />
            Rewrite
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
