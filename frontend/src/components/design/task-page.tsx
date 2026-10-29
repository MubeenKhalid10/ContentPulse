"use client";

import { LoaderCircleIcon, LockIcon, PencilIcon, RotateCcwIcon, SparklesIcon } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { POST_STATUS_TONE } from "@/lib/tones";
import { BackLink, useFromHere } from "@/components/shared/back-link";
import { PostProgress } from "@/components/shared/post-progress";
import { PlatformTag, Tag } from "@/components/shared/tag";
import { ReviewBanner } from "@/components/approvals/review-banner";
import { BriefDialog } from "@/components/design/brief-dialog";
import { CreativeUploader, CreativeVersions } from "@/components/design/creatives";
import { PostColors } from "@/components/design/post-colors";
import { PostLogo } from "@/components/design/post-logo";
import { DeleteButton } from "@/components/shared/delete-button";
import { SimpleSelect } from "@/components/shared/simple-select";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ArticlePreview } from "@/components/content/article-preview";
import { HandoffButtons } from "@/components/design/handoff-buttons";
import { useDeletePost } from "@/hooks/use-content";
import { useAssignTask, useDeleteDesign, useDesignTask, useWithdrawDesign } from "@/hooks/use-design";
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
import { useMembers } from "@/hooks/use-organization";
import { ApiError, errorMessage } from "@/lib/api";
import { useCan, useMe } from "@/lib/auth";
import { POST_STATUS_LABEL, fullText } from "@/lib/content";
import { formatLabel } from "@/lib/design";
import { cn } from "@/lib/utils";
import type { DesignTaskDetail } from "@/types/api";

const ACTIVE = ["open", "assigned", "in_progress"];
const UPLOADABLE_POST = ["design_pending", "design_in_progress", "design_uploaded", "changes_requested"];

export function DesignTaskPage({ id }: { id: string }) {
  const task = useDesignTask(id);
  const me = useMe();
  const can = useCan();
  const fromHere = useFromHere();
  const [editing, setEditing] = useState(false);

  const back = <BackLink href="/design" label="Design" />;
  if (task.isError) {
    const notFound = task.error instanceof ApiError && task.error.status === 404;
    return (
      <>
        {back}
        <Alert variant="destructive">
          <AlertDescription>{notFound ? "This task doesn't exist or isn't in your organization." : errorMessage(task.error)}</AlertDescription>
        </Alert>
      </>
    );
  }
  if (!task.data) {
    return (
      <>
        {back}
        <Skeleton className="h-10 w-2/3" />
        <div className="mt-6 grid gap-6 lg:grid-cols-3">
          <Skeleton className="h-[30rem] lg:col-span-2" />
          <Skeleton className="h-72" />
        </div>
      </>
    );
  }

  const t = task.data;
  const active = ACTIVE.includes(t.status);
  const mine = t.assignee?.id === me.data?.id;
  const manager = can("design.manage");
  const canReview = can("approval.manage");
  // Only the assignee works on an assigned task (anyone when it is unassigned); an admin can step in.
  const assignedToOther = !!t.assignee && !mine && !manager;
  const canWork =
    can("design.upload") && active && !assignedToOther && UPLOADABLE_POST.includes(t.post.status);
  const canWithdraw =
    can("design.upload") && t.status === "submitted" && t.review?.status === "pending" && (mine || manager || !t.assignee);
  const canEditBrief = (can("content.edit") || manager) && active;

  return (
    <>
      {back}
      <div className="mb-6 flex flex-wrap items-start gap-4">
        <div className="grid min-w-0 flex-1 gap-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">{t.post.title ?? "Untitled post"}</h1>
            <PlatformTag platform={t.post.platform} />
            <Tag tone={POST_STATUS_TONE[t.post.status]} dot>{POST_STATUS_LABEL[t.post.status]}</Tag>
          </div>
          <p className="text-sm text-muted-foreground">
            {formatLabel(t.format)}
            {t.dimensions && ` · ${t.dimensions}`}
          </p>
        </div>
        <TaskActions task={t} manager={manager} mine={mine} />
      </div>

      <PostProgress status={t.post.status} />

      <ReviewBanner review={t.review} />
      {t.status === "submitted" && t.review?.status === "pending" && (
        <Alert className="mb-6">
          <AlertTitle>Waiting for design approval</AlertTitle>
          <AlertDescription className="grid gap-2">
            <span>
              The design is locked while an admin reviews it. They will approve it or ask for changes, and you&apos;ll
              see the decision here.
              {canWithdraw && " Need to change something first? Take it back and submit it again when you are done."}
            </span>
            {canWithdraw && <WithdrawButton taskId={t.id} />}
          </AlertDescription>
        </Alert>
      )}
      {assignedToOther && active && (
        <Alert className="mb-6">
          <LockIcon />
          <AlertTitle>Assigned to {t.assignee?.name ?? t.assignee?.email}</AlertTitle>
          <AlertDescription>
            Only they or an admin can add the design for this post. Ask an admin to reassign it if you should take it.
          </AlertDescription>
        </Alert>
      )}
      {t.status === "completed" && (
        <Alert className="mb-6">
          <LockIcon />
          <AlertTitle>Approved design is locked</AlertTitle>
          <AlertDescription className="grid gap-2">
            <span>
              {canReview
                ? "Request changes to let the creator update the design again."
                : "An admin can request changes to reopen it."}
            </span>
            {canReview && t.review?.status === "approved" && (
              <Link
                href={fromHere(`/approvals/${t.review.request_id}`)}
                className={cn(buttonVariants({ size: "sm", variant: "outline" }), "w-fit")}
              >
                <RotateCcwIcon />
                Request changes
              </Link>
            )}
          </AlertDescription>
        </Alert>
      )}
      {t.status === "cancelled" && (
        <Alert className="mb-6">
          <AlertTitle>{t.post.status === "rejected" ? "Post rejected" : "Closed"}</AlertTitle>
          <AlertDescription>
            {t.post.status === "rejected"
              ? "The post was rejected, so this design task is closed."
              : "The post was taken back from design. A new task opens when its copy is approved again."}
          </AlertDescription>
        </Alert>
      )}

      {/* Design first: this is the designer's page; the copy it goes with follows. */}
      <div className="grid gap-8">
        <section aria-labelledby="design-group" className="grid gap-4">
          <div className="grid gap-1 border-b pb-2">
            <h2 id="design-group" className="text-lg font-semibold">
              Design
            </h2>
            <p className="text-sm text-muted-foreground">The brief, your brand rules and the design files for this post.</p>
          </div>
          <div className="grid gap-6 lg:grid-cols-3">
            <div className="grid min-w-0 grid-cols-1 content-start gap-6 lg:col-span-2">
              <BriefCard task={t} canEdit={canEditBrief} onEdit={() => setEditing(true)} />
              <BrandCard task={t} canEdit={canEditBrief} canEditBrand={can("organization.write")} />
            </div>
            <div className="grid min-w-0 grid-cols-1 content-start gap-6">
              {canWork && <CreativeUploader task={t} canSubmit={can("design.submit")} />}
              <CreativeVersions task={t} canUse={canWork} />
              {!canWork && !t.creatives.length && (
                <p className="rounded-xl border border-dashed p-6 text-center text-sm text-muted-foreground">
                  No design files uploaded yet.
                </p>
              )}
            </div>
          </div>
        </section>

        <ContentCard task={t} />
      </div>
      <BriefDialog task={t} open={editing} onClose={() => setEditing(false)} />
    </>
  );
}

function WithdrawButton({ taskId }: { taskId: string }) {
  const [open, setOpen] = useState(false);
  const withdraw = useWithdrawDesign();
  return (
    <>
      <Button size="sm" variant="outline" className="w-fit" onClick={() => setOpen(true)} disabled={withdraw.isPending}>
        <RotateCcwIcon />
        Withdraw to make changes
      </Button>
      <AlertDialog open={open} onOpenChange={setOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Take the design back?</AlertDialogTitle>
            <AlertDialogDescription>
              It leaves the admin&apos;s approval queue and you can change the files again. Submit it again when it is
              ready.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep it submitted</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                setOpen(false);
                withdraw.mutate(taskId, {
                  onSuccess: () => toast.success("Design withdrawn. You can change it now."),
                  onError: (e) => toast.error(errorMessage(e)),
                });
              }}
            >
              Withdraw
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

// While the design is being made or revised its files can be deleted; once it is waiting for
// approval or approved, the admin requests changes first (or deletes the post).
const DESIGN_DELETABLE = ["design_pending", "design_in_progress", "design_uploaded", "changes_requested"];

function TaskActions({ task, manager, mine }: { task: DesignTaskDetail; manager: boolean; mine: boolean }) {
  const members = useMembers();
  const assign = useAssignTask();
  const isAdmin = useCan()("organization.write");
  const removeDesign = useDeleteDesign();
  const removePost = useDeletePost();
  const router = useRouter();
  const active = ACTIVE.includes(task.status);
  const onError = (e: unknown) => toast.error(errorMessage(e));
  const people = (members.data ?? []).filter((m) => m.status === "active" && (m.role === "creator" || m.role === "admin"));

  return (
    <div className="flex flex-wrap items-center gap-x-1.5 gap-y-2">
      {active && manager && <span className="text-sm text-muted-foreground">Assigned to</span>}
      {active && manager ? (
        <SimpleSelect
          id="task-assignee"
          aria-label="Assigned to"
          value={task.assignee?.id ?? "none"}
          onChange={(v) =>
            assign.mutate(
              { id: task.id, assigneeId: v === "none" ? null : v },
              { onSuccess: (t) => toast.success(t.assignee ? `Assigned to ${t.assignee.name ?? t.assignee.email}` : "Unassigned"), onError },
            )
          }
          options={[{ value: "none", label: "Un-Assigned" }, ...people.map((m) => ({ value: m.user_id, label: m.full_name ?? m.email }))]}
          className="w-60"
        />
      ) : (
        task.assignee && (
          <span className="text-sm text-muted-foreground">
            {mine ? "You're on this" : `${task.assignee.name ?? task.assignee.email} is on this`}
          </span>
        )
      )}
      {isAdmin && (
        <span aria-hidden className="mx-1 hidden h-5 w-px bg-border sm:block" />
      )}
      {isAdmin && task.creatives.length > 0 && DESIGN_DELETABLE.includes(task.post.status) && (
        <DeleteButton
          label="Delete design"
          title="Delete the uploaded design?"
          description="This permanently deletes every uploaded design file and version for this post so the design can be done again. The copy and approvals are kept. This can't be undone."
          pending={removeDesign.isPending}
          onConfirm={() =>
            removeDesign.mutate(task.id, {
              onSuccess: () => toast.success("Design deleted"),
              onError,
            })
          }
        />
      )}
      {isAdmin && (
        <DeleteButton
          label="Delete post"
          title={`Delete “${task.post.title ?? "this post"}”?`}
          description="This permanently deletes the post and everything attached to it: every version of the copy, its design task and files, and its approvals. The plan it came from is kept. This can't be undone."
          pending={removePost.isPending}
          onConfirm={() =>
            removePost.mutate(task.post.id, {
              onSuccess: () => {
                toast.success("Post deleted");
                router.push("/design");
              },
              onError,
            })
          }
        />
      )}
    </div>
  );
}

function BriefCard({ task: t, canEdit, onEdit }: { task: DesignTaskDetail; canEdit: boolean; onEdit: () => void }) {
  const rows: [string, React.ReactNode][] = [
    ["Format", `${formatLabel(t.format)}${t.dimensions ? ` · ${t.dimensions}` : ""}`],
    ["Headline", t.headline],
    ["Supporting text", t.supporting_text],
    ["Visual direction", t.visual_concept],
    ["Call to action", t.cta],
    ["Notes", t.designer_notes],
  ];
  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-start gap-2">
        <div className="grid flex-1 gap-1">
          <CardTitle>Design brief</CardTitle>
          <CardDescription className="flex items-center gap-1.5" role={t.ai_brief_pending ? "status" : undefined}>
            {t.ai_brief_pending ? (
              <>
                <LoaderCircleIcon className="size-3.5 animate-spin" />
                The AI is refining this brief…
              </>
            ) : t.source === "ai" ? (
              <>
                <SparklesIcon className="size-3.5" />
                Written by AI from the post
              </>
            ) : t.source === "edited" ? (
              "Edited by your team"
            ) : (
              "Built from the post"
            )}
          </CardDescription>
        </div>
        <HandoffButtons id={t.id} />
        {canEdit && (
          <Button size="sm" variant="ghost" onClick={onEdit}>
            <PencilIcon />
            Edit brief
          </Button>
        )}
      </CardHeader>
      <CardContent className="grid gap-5">
        <dl className="grid gap-x-4 gap-y-2.5 text-sm sm:grid-cols-[9rem_1fr]">
          {rows
            .filter(([, value]) => value)
            .map(([label, value]) => (
              <div key={label} className="contents">
                <dt className="text-muted-foreground">{label}</dt>
                <dd className="whitespace-pre-wrap">{value}</dd>
              </div>
            ))}
        </dl>
        {t.slide_structure.length > 0 && (
          <section aria-label="Slides" className="grid gap-1.5">
            <h3 className="text-sm font-medium">{t.format === "carousel" ? "Slides" : "Structure"}</h3>
            <ol className="grid gap-1 text-sm">
              {t.slide_structure.map((s, i) => (
                <li key={i} className="rounded-lg bg-muted/50 px-3 py-1.5">
                  {s}
                </li>
              ))}
            </ol>
          </section>
        )}
        {t.visual_elements.length > 0 && (
          <section aria-label="Visual elements" className="grid gap-1.5">
            <h3 className="text-sm font-medium">Visual elements</h3>
            <ul className="flex flex-wrap gap-1.5">
              {t.visual_elements.map((e) => (
                <li key={e}>
                  <Badge variant="outline">{e}</Badge>
                </li>
              ))}
            </ul>
          </section>
        )}
      </CardContent>
    </Card>
  );
}

function ContentCard({ task: t }: { task: DesignTaskDetail }) {
  if (!t.content) return null;
  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-start gap-2">
        <div className="grid flex-1 gap-1">
          <CardTitle>Post content</CardTitle>
          <CardDescription>
            Version {t.content.version}
            {t.post.topic_title && ` · ${t.post.topic_title}`}
          </CardDescription>
        </div>
      </CardHeader>
      <CardContent>
        {t.post.platform === "blog" ? (
          <div className="max-h-[24rem] overflow-y-auto">
            <ArticlePreview
              title={t.post.title}
              seo={t.content.blog}
              intro={t.content.hook}
              body={t.content.body}
              cta={t.content.cta}
            />
          </div>
        ) : (
          <p className="rounded-lg bg-muted/50 p-3 text-sm whitespace-pre-wrap">
            {fullText(t.content.hook, t.content.body, t.content.cta, t.content.hashtags)}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function BrandCard({
  task: t,
  canEdit,
  canEditBrand,
}: {
  task: DesignTaskDetail;
  canEdit: boolean;
  canEditBrand: boolean;
}) {
  const req = t.brand_requirements;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Brand guidelines</CardTitle>
        <CardDescription>
          From your Brand settings.{" "}
          {!t.brand.colors.length && !t.brand.typography && (
            <Link href="/organization/brand" className="underline underline-offset-4">
              Add colors and typography
            </Link>
          )}
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4 text-sm">
        <PostColors task={t} canEdit={canEdit} />
        <PostLogo task={t} canEdit={canEdit} canEditBrand={canEditBrand} />
        <dl className="grid gap-x-4 gap-y-2 sm:grid-cols-[9rem_1fr]">
          {[
            ["Typography", req.typography ?? t.brand.typography],
            ["Voice", t.brand.brand_voice],
            ["Tone", t.brand.tone],
            ["Requirements", req.requirements?.join(" · ")],
            ["Forbidden terms", (req.avoid_terms ?? t.brand.forbidden_terms).join(", ")],
          ]
            .filter(([, v]) => v)
            .map(([label, value]) => (
              <div key={label} className="contents">
                <dt className="text-muted-foreground">{label}</dt>
                <dd>{value}</dd>
              </div>
            ))}
        </dl>
      </CardContent>
    </Card>
  );
}
