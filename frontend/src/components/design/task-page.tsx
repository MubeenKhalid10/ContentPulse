"use client";

import { ArrowLeftIcon, LoaderCircleIcon, PencilIcon, SparklesIcon } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { POST_STATUS_TONE } from "@/lib/tones";
import { PlatformTag, Tag } from "@/components/shared/tag";
import { ReviewBanner } from "@/components/approvals/review-banner";
import { BriefDialog } from "@/components/design/brief-dialog";
import { CreativeUploader, CreativeVersions } from "@/components/design/creatives";
import { SimpleSelect } from "@/components/shared/simple-select";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ArticlePreview } from "@/components/content/article-preview";
import { useAssignTask, useDesignTask } from "@/hooks/use-design";
import { useMembers } from "@/hooks/use-organization";
import { ApiError, errorMessage } from "@/lib/api";
import { useCan, useMe } from "@/lib/auth";
import { POST_STATUS_LABEL, fullText } from "@/lib/content";
import { formatLabel } from "@/lib/design";
import type { DesignTaskDetail } from "@/types/api";

const ACTIVE = ["open", "assigned", "in_progress"];
const UPLOADABLE_POST = ["design_pending", "design_in_progress", "design_uploaded", "changes_requested"];

export function DesignTaskPage({ id }: { id: string }) {
  const task = useDesignTask(id);
  const me = useMe();
  const can = useCan();
  const [editing, setEditing] = useState(false);

  const back = (
    <Link href="/design" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
      <ArrowLeftIcon className="size-4" />
      Design
    </Link>
  );
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
  // Any creator can deliver; the assignee only shows who is on it.
  const canWork = can("design.upload") && active && UPLOADABLE_POST.includes(t.post.status);
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

      <ReviewBanner review={t.review} />
      {t.status === "submitted" && t.review?.status === "pending" && (
        <Alert className="mb-6">
          <AlertTitle>Waiting for approval</AlertTitle>
          <AlertDescription>An admin will approve the post or ask for changes. You&apos;ll see their decision here.</AlertDescription>
        </Alert>
      )}
      {t.status === "cancelled" && (
        <Alert className="mb-6">
          <AlertTitle>{t.post.status === "rejected" ? "Post rejected" : "Closed"}</AlertTitle>
          <AlertDescription>
            {t.post.status === "rejected"
              ? "The post was rejected, so this design task is closed."
              : "The post was taken back from design. A new task opens when it's sent to design again."}
          </AlertDescription>
        </Alert>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="grid min-w-0 grid-cols-1 content-start gap-6 lg:col-span-2">
          <BriefCard task={t} canEdit={canEditBrief} onEdit={() => setEditing(true)} />
          <ContentCard task={t} />
          <BrandCard task={t} />
        </div>
        <div className="grid min-w-0 grid-cols-1 content-start gap-6">
          {canWork && <CreativeUploader task={t} canSubmit={can("design.submit")} />}
          <CreativeVersions task={t} />
          {!canWork && !t.creatives.length && (
            <p className="rounded-xl border border-dashed p-6 text-center text-sm text-muted-foreground">No creative uploaded yet.</p>
          )}
        </div>
      </div>
      <BriefDialog task={t} open={editing} onClose={() => setEditing(false)} />
    </>
  );
}

function TaskActions({ task, manager, mine }: { task: DesignTaskDetail; manager: boolean; mine: boolean }) {
  const members = useMembers();
  const assign = useAssignTask();
  const active = ACTIVE.includes(task.status);
  const onError = (e: unknown) => toast.error(errorMessage(e));
  const people = (members.data ?? []).filter((m) => m.status === "active" && (m.role === "creator" || m.role === "admin"));

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {active && manager ? (
        <SimpleSelect
          aria-label="Assignee"
          value={task.assignee?.id ?? "none"}
          onChange={(v) =>
            assign.mutate(
              { id: task.id, assigneeId: v === "none" ? null : v },
              { onSuccess: (t) => toast.success(t.assignee ? `Assigned to ${t.assignee.name ?? t.assignee.email}` : "Unassigned"), onError },
            )
          }
          options={[{ value: "none", label: "Anyone can take it" }, ...people.map((m) => ({ value: m.user_id, label: m.full_name ?? m.email }))]}
          className="w-48"
        />
      ) : (
        task.assignee && (
          <span className="text-sm text-muted-foreground">
            {mine ? "You're on this" : `${task.assignee.name ?? task.assignee.email} is on this`}
          </span>
        )
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
          <CardDescription className="flex items-center gap-1.5">
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
          <CardTitle>Post copy</CardTitle>
          <CardDescription>
            Version {t.content.version}
            {t.post.topic_title && ` · ${t.post.topic_title}`}
          </CardDescription>
        </div>
      </CardHeader>
      <CardContent>
        {t.post.platform === "blog" ? (
          <div className="max-h-[36rem] overflow-y-auto">
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

function BrandCard({ task: t }: { task: DesignTaskDetail }) {
  const req = t.brand_requirements;
  const colors = req.colors?.length ? req.colors : t.brand.colors;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Brand guidelines</CardTitle>
        <CardDescription>
          From your Brand settings.{" "}
          {!colors.length && !t.brand.typography && (
            <Link href="/organization/brand" className="underline underline-offset-4">
              Add colors and typography
            </Link>
          )}
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4 text-sm">
        {colors.length > 0 && (
          <ul className="flex flex-wrap gap-3" aria-label="Brand colors">
            {colors.map((c) => (
              <li key={c} className="flex items-center gap-2">
                <span className="size-6 rounded-md ring-1 ring-foreground/10" style={{ background: c }} aria-hidden />
                <span className="font-mono text-xs">{c}</span>
              </li>
            ))}
          </ul>
        )}
        <dl className="grid gap-x-4 gap-y-2 sm:grid-cols-[9rem_1fr]">
          {[
            ["Typography", req.typography ?? t.brand.typography],
            ["Voice", t.brand.brand_voice],
            ["Tone", t.brand.tone],
            ["Requirements", req.requirements?.join(" · ")],
            ["Never use", (req.avoid_terms ?? t.brand.forbidden_terms).join(", ")],
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
