"use client";

import { CheckIcon, DownloadIcon, FlagIcon, MessageSquarePlusIcon, PaletteIcon, RotateCcwIcon, XIcon } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { APPROVAL_STATUS_TONE } from "@/lib/tones";
import { BackLink, useFromHere } from "@/components/shared/back-link";
import { PlatformTag, Tag } from "@/components/shared/tag";
import { ArticlePreview } from "@/components/content/article-preview";
import { SocialPostPreview } from "@/components/content/social-preview";
import { SharePostButton } from "@/components/content/share-post-button";
import { HandoffButtons } from "@/components/design/handoff-buttons";
import { Alert, AlertDescription } from "@/components/ui/alert";
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
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useAddComment, useApproval, useApprove, useFinalize, useReject, useRequestChanges } from "@/hooks/use-approvals";
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
          <AlertDescription>{notFound ? "This submission doesn't exist or isn't in your organization." : errorMessage(approval.error)}</AlertDescription>
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
          <Alert>
            <AlertDescription>The copy has changed since this submission (now version {a.post.current_version}).</AlertDescription>
          </Alert>
        )}
        {a.post.platform === "blog" ? (
          <div className="mx-auto grid w-full max-w-2xl gap-3">
            {files[0]?.file_type.startsWith("image/") && (
              // Signed, short-lived URLs: next/image can't optimize them.
              // eslint-disable-next-line @next/next/no-img-element
              <img src={files[0].url} alt="Featured image" className="aspect-[1.91/1] w-full rounded-xl border object-cover" />
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
          <ul className="grid gap-1 text-xs text-amber-700 dark:text-amber-400" aria-label="Copy checks">
            {a.content!.meta.warnings!.map((w) => (
              <li key={w}>⚠ {w}</li>
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

function DecisionCard({ approval: a }: { approval: ApprovalDetail }) {
  const fromHere = useFromHere();
  const can = useCan()("approval.manage");
  const approve = useApprove();
  const changes = useRequestChanges();
  const reject = useReject();
  const finalize = useFinalize();
  // Each decision has its own comment, so text never goes out with the wrong button.
  const [changesOpen, setChangesOpen] = useState(false);
  const [changeNote, setChangeNote] = useState("");
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectNote, setRejectNote] = useState("");
  const router = useRouter();
  const busy = approve.isPending || changes.isPending || reject.isPending;
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

  if (a.status !== "pending") {
    return (
      <Card>
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
            ? "Approving the content sends it to design, with a brief and guidelines your designer can export. "
            : "Approving makes the post ready to publish. "}
          Checking copy v{a.post_version}
          {a.creative_version != null && ` and design v${a.creative_version}`}.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-2">
        <Button
          disabled={busy}
          onClick={() =>
            approve.mutate(
              { id: a.id, comment: "" },
              {
                onSuccess: () => {
                  toast.success(
                    a.stage === "copy"
                      ? "Content approved. Its design brief is ready on the Design page."
                      : "Approved: the post is in Ready to post.",
                  );
                  void openNext();
                },
                onError,
              },
            )
          }
        >
          <CheckIcon />
          {a.stage === "copy" ? "Approve content" : "Approve"}
        </Button>
        <Button variant="outline" disabled={busy} onClick={() => setChangesOpen(true)}>
          <RotateCcwIcon />
          Request changes
        </Button>
        <Button variant="ghost" className="text-destructive" disabled={busy} onClick={() => setRejectOpen(true)}>
          <XIcon />
          Reject
        </Button>
      </CardContent>

      <AlertDialog open={changesOpen} onOpenChange={setChangesOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>What should change?</AlertDialogTitle>
            <AlertDialogDescription>
              {a.stage === "copy"
                ? "The post goes back to its writer to revise the copy, then they submit it again."
                : "The post goes back to its creator, who can fix the copy, the design or both, then resubmit it."}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <Textarea
            aria-label="What should change"
            rows={4}
            maxLength={4000}
            placeholder="e.g. Shorten the headline and use the brand blue on slide 3."
            value={changeNote}
            onChange={(e) => setChangeNote(e.target.value)}
          />
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              disabled={!changeNote.trim() || busy}
              onClick={() =>
                changes.mutate(
                  { id: a.id, comment: changeNote.trim(), scope: "both" },
                  {
                    onSuccess: () => {
                      toast.success("Changes requested");
                      setChangeNote("");
                      setChangesOpen(false);
                    },
                    onError,
                  },
                )
              }
            >
              Request changes
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={rejectOpen} onOpenChange={setRejectOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Reject this post?</AlertDialogTitle>
            <AlertDialogDescription>
              The post leaves the workflow for good. To get a revision instead, request changes.
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
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
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
              Reject post
            </AlertDialogAction>
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
              <li key={c.id} className={cn("grid gap-1 rounded-lg p-3 text-sm", c.approval_request_id === a.id ? "bg-muted/60" : "bg-muted/30 opacity-80")}>
                <span className="flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
                  <span className="font-medium text-foreground">{c.author?.name ?? c.author?.email ?? "Someone"}</span>
                  {COMMENT_KIND_LABEL[c.kind]}
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
            <Button type="submit" size="sm" variant="outline" className="justify-self-end" disabled={!body.trim() || add.isPending}>
              <MessageSquarePlusIcon />
              Comment
            </Button>
          </form>
        )}
      </CardContent>
    </Card>
  );
}

