"use client";

import {
  CheckCircle2Icon,
  ChevronRightIcon,
  ClipboardListIcon,
  CopyIcon,
  type LucideIcon,
  SquarePenIcon,
  LoaderCircleIcon,
  PencilIcon,
  PlusIcon,
  SparklesIcon,
} from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { POST_STATUS_TONE, TOPIC_STATUS_TONE } from "@/lib/tones";
import { BackLink, useFromHere } from "@/components/shared/back-link";
import { CollapsibleCard } from "@/components/shared/collapsible-card";
import { DeleteButton } from "@/components/shared/delete-button";
import { PlatformTag, Tag } from "@/components/shared/tag";
import { EditTopicDialog } from "@/components/topics/edit-topic-dialog";
import { StrategyCard } from "@/components/topics/strategy-card";
import { StrategyDialog } from "@/components/topics/strategy-dialog";
import { TopicActions } from "@/components/topics/topic-actions";
import { AlignmentPanel } from "@/components/trends/alignment-panel";
import { RelevanceBadge } from "@/components/trends/relevance";
import { Score, SignalBreakdown } from "@/components/trends/score";
import { groupBySource, MentionItem } from "@/components/trends/mentions";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useDeletePost, usePosts, useWriteAll } from "@/hooks/use-content";
import { useTopic } from "@/hooks/use-topics";
import { useMarkets } from "@/hooks/use-trends";
import { ApiError, errorMessage } from "@/lib/api";
import { useCan } from "@/lib/auth";
import { POST_STATUS_LABEL } from "@/lib/content";
import { formatDateTime, stripCitations, timeAgo } from "@/lib/format";
import { PLATFORM_LABEL, TOPIC_STATUS_LABEL } from "@/lib/topics";
import { sourceName } from "@/lib/trends";
import { cn } from "@/lib/utils";
import type {
  ContentAngle,
  Platform,
  PlatformFit,
  Post,
  Strategy,
  TopicDetail,
} from "@/types/api";

export function TopicDetailView({ id }: { id: string }) {
  const fromHere = useFromHere();
  const topic = useTopic(id);
  const markets = useMarkets();
  const can = useCan();
  const canManage = can("topics.manage");
  const marketNames = useMemo(
    () => new Map(markets.data?.map((m) => [m.code, m.name])),
    [markets.data],
  );
  const [dialog, setDialog] = useState<{
    platform: Platform | null;
    editing: Strategy | null;
    angle?: ContentAngle;
  } | null>(null);
  const [autoPlan, setAutoPlan] = useState(
    () => typeof window !== "undefined" && new URLSearchParams(window.location.search).get("plan") === "1",
  );
  const [editing, setEditing] = useState(false);

  const back = <BackLink href="/topics" label="Shortlist & plans" />;

  if (topic.isError) {
    const notFound =
      topic.error instanceof ApiError && topic.error.status === 404;
    return (
      <>
        {back}
        <Alert variant="destructive">
          <AlertDescription className="flex flex-wrap items-center gap-3">
            <span>
              {notFound
                ? "This trend doesn't exist or isn't in your organization."
                : errorMessage(topic.error)}
            </span>
            {!notFound && (
              <Button size="sm" variant="outline" onClick={() => topic.refetch()}>
                Try again
              </Button>
            )}
          </AlertDescription>
        </Alert>
      </>
    );
  }
  if (!topic.data) {
    return (
      <>
        {back}
        <Skeleton className="h-10 w-2/3" />
        <div className="mt-6 grid gap-6 lg:grid-cols-3">
          <Skeleton className="h-96 lg:col-span-2" />
          <Skeleton className="h-64" />
        </div>
      </>
    );
  }

  const t = topic.data;
  const trend = t.trend;
  const shortlisted = t.status === "shortlisted";
  const plan = (platform: Platform | null) =>
    setDialog({ platform, editing: null });

  return (
    <>
      {back}
      <div className="mb-8 flex flex-wrap items-start gap-4">
        <Score score={t.opportunity_score} size="lg" />
        <div className="grid min-w-0 flex-1 gap-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">{t.title}</h1>
            <Tag tone={TOPIC_STATUS_TONE[t.status]} dot>
              {TOPIC_STATUS_LABEL[t.status]}
            </Tag>
            <RelevanceBadge level={t.relevance_level} />
            {canManage && t.status !== "archived" && (
              <Button
                size="icon-sm"
                variant="ghost"
                aria-label="Edit topic"
                title="Edit topic"
                onClick={() => setEditing(true)}
              >
                <PencilIcon />
              </Button>
            )}
          </div>
        </div>
        {canManage && <TopicActions topic={t} />}
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="grid content-start gap-6 lg:col-span-2">
          <StrategiesCard
            topic={t}
            canManage={canManage}
            onPlan={plan}
            onEdit={(s) => setDialog({ platform: s.platform, editing: s })}
          />
          {can("content.read") && <TopicPosts topicId={t.id} />}
          {trend ? (
            <AlignmentPanel
              trend={trend}
              canReview={canManage}
              onPlanAngle={
                canManage && shortlisted
                  ? (angle) =>
                      setDialog({
                        platform:
                          (angle.platforms[0] as Platform | undefined) ?? null,
                        editing: null,
                        angle,
                      })
                  : undefined
              }
            />
          ) : (
            t.relevance_reason && (
              <Card>
                <CardHeader>
                  <CardTitle>Does this fit your business?</CardTitle>
                  <CardDescription>
                    How this connects to your website and services.
                  </CardDescription>
                </CardHeader>
                <CardContent className="text-sm">
                  {stripCitations(t.relevance_reason)}
                </CardContent>
              </Card>
            )
          )}
          {trend && (
            <CollapsibleCard
              title="Why it's trending"
              description="The signals behind the opportunity score."
            >
              <SignalBreakdown signals={trend.signals} />
            </CollapsibleCard>
          )}
          {trend && trend.mentions.length > 0 && (
            <CollapsibleCard
              title="Sources"
              count={trend.mentions.length}
              description="Where this trend is being discussed."
              contentClassName="grid gap-6"
            >
              {(
                <>
                  {groupBySource(trend.mentions).map(([source, mentions]) => (
                    <section
                      key={source}
                      aria-label={sourceName(source)}
                      className="grid gap-2"
                    >
                      <h2 className="text-sm font-medium">
                        {sourceName(source)}{" "}
                        <span className="font-normal text-muted-foreground">
                          ({mentions.length})
                        </span>
                      </h2>
                      <ul className="grid gap-2">
                        {mentions.slice(0, 4).map((m) => (
                          <MentionItem
                            key={m.id}
                            mention={m}
                            marketNames={marketNames}
                          />
                        ))}
                      </ul>
                      {mentions.length > 4 && (
                        <p className="text-xs text-muted-foreground">
                          Showing 4 of {mentions.length}
                        </p>
                      )}
                    </section>
                  ))}
                  <Link
                    href={fromHere(`/trends/${trend.id}`)}
                    className="text-sm underline-offset-4 hover:underline"
                  >
                    See the full trend
                  </Link>
                </>
              )}
            </CollapsibleCard>
          )}
        </div>

        <div className="grid content-start gap-6">
          <PlatformFitCard
            fit={t.platform_fit}
            recommended={t.recommended_platforms}
            canPlan={canManage && shortlisted}
            onPlan={plan}
          />
        </div>
      </div>

      <StrategyDialog
        topic={t}
        open={!!dialog || (autoPlan && canManage && shortlisted)}
        platform={dialog?.platform ?? null}
        editing={dialog?.editing ?? null}
        angle={dialog?.angle ?? null}
        onClose={() => {
          setDialog(null);
          if (autoPlan) {
            setAutoPlan(false);
            window.history.replaceState(null, "", window.location.pathname);
          }
        }}
      />
      <EditTopicDialog
        topic={t}
        open={editing}
        onClose={() => setEditing(false)}
      />
    </>
  );
}

export function StrategiesCard({
  topic,
  canManage,
  onPlan,
  onEdit,
}: {
  topic: TopicDetail;
  canManage: boolean;
  onPlan: (platform: Platform | null) => void;
  onEdit: (strategy: Strategy) => void;
}) {
  const shortlisted = topic.status === "shortlisted";
  const strategies = [...topic.strategies].sort(
    (a, b) => Number(a.status === "archived") - Number(b.status === "archived"),
  );
  // Same query as the Posts card below (shared cache): the post each plan led to.
  const posts = usePosts(
    { status: "all", platform: "", topicId: topic.id, q: "" },
    50,
  );
  const canGenerate = useCan()("content.generate");
  const writeAll = useWriteAll();
  // A plan that already has a post is shown in the Posts card instead.
  const unwritten = strategies.filter(
    (s) =>
      !(posts.data?.items ?? []).some((p) => p.content_strategy_id === s.id),
  );
  const toWrite = unwritten.filter((s) => s.status !== "archived");
  const hasPlans = strategies.length > 0;
  const canCreate = canManage && shortlisted;
  return (
    <Card>
      <CardHeader>
        <SectionHeader
          icon={ClipboardListIcon}
          title="Post plans"
          description="Each plan sets the platform, audience, message and goal of one post."
          badge={`${strategies.length} ${strategies.length === 1 ? "plan" : "plans"}`}
          actions={
            hasPlans && canCreate && unwritten.length > 0 ? (
              <>
                {canGenerate && toWrite.length > 1 && (
                  <Button
                    size="sm"
                    disabled={writeAll.isPending}
                    onClick={() =>
                      writeAll.mutate(
                        toWrite.map((s) => s.id),
                        {
                          onError: (e) => toast.error(errorMessage(e)),
                          onSuccess: (r) =>
                            r.failed
                              ? toast.error(
                                  `Started ${r.ok}, but ${r.failed} failed: ${errorMessage(r.error)}`,
                                )
                              : toast.success(
                                  `Writing ${r.ok} posts, one per platform. They stay together in Write posts.`,
                                ),
                        },
                      )
                    }
                  >
                    <SparklesIcon />
                    {writeAll.isPending ? "Starting…" : `Write all ${toWrite.length} posts`}
                  </Button>
                )}
                <Button
                  size="sm"
                  variant={toWrite.length > 1 && canGenerate ? "outline" : "default"}
                  onClick={() => onPlan(null)}
                >
                  <PlusIcon />
                  Create plan
                </Button>
              </>
            ) : null
          }
        />
      </CardHeader>
      <CardContent className="grid gap-3">
        {unwritten.length ? (
          unwritten.map((s) => (
            <StrategyCard
              key={s.id}
              strategy={s}
              canManage={canManage && shortlisted}
              onEdit={() => onEdit(s)}
            />
          ))
        ) : hasPlans ? (
          <div className="grid justify-items-center gap-3 rounded-lg border border-dashed p-5 text-center">
            <p className="text-sm text-muted-foreground">
              Every plan has a post. Review them under Generated posts below.
            </p>
            {canCreate && (
              <Button size="sm" onClick={() => onPlan(null)}>
                <PlusIcon />
                Create plan
              </Button>
            )}
          </div>
        ) : shortlisted ? (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-dashed p-3">
            <p className="flex min-w-0 flex-1 items-center gap-2 text-sm text-muted-foreground">
              <SquarePenIcon aria-hidden className="size-4 shrink-0" />
              Choose where to publish, who you&apos;re targeting, and what the post should achieve.
            </p>
            {canCreate && (
              <Button size="sm" onClick={() => onPlan(null)}>
                <PlusIcon />
                Create your first plan
              </Button>
            )}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            Plans can be made once the trend is shortlisted.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

const POST_DESCRIPTION =
  "This permanently deletes the post and everything attached to it: every version of the copy, its design task and files, and its approvals. The plan it came from is kept. This can't be undone.";

export function TopicPosts({ topicId }: { topicId: string }) {
  const fromHere = useFromHere();
  const posts = usePosts({ status: "all", platform: "", topicId, q: "" }, 50);
  if (!posts.data) return null;
  const items = posts.data.items;
  return (
    <Card>
      <CardHeader>
        <SectionHeader
          icon={CopyIcon}
          title="Generated posts"
          description="Posts created from your plans, with their current review status."
          badge={`${items.length} ${items.length === 1 ? "post" : "posts"}`}
        />
      </CardHeader>
      <CardContent className="grid gap-3">
        {items.length ? (
          <>
            <ul className="grid gap-2" aria-label="Generated posts">
              {items.map((p) => (
                <GeneratedPost key={p.id} post={p} href={fromHere(`/posts/${p.id}`)} />
              ))}
            </ul>
            <p className="text-xs text-muted-foreground">
              Select a post to open it in the studio, review its content, and continue the workflow
              according to its current status.
            </p>
          </>
        ) : (
          <p className="rounded-lg border border-dashed p-4 text-center text-sm text-muted-foreground">
            No posts yet. Posts appear here once you generate one from a plan.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

/** One generated post: platform and title, a preview, then its status, version and date. */
function GeneratedPost({ post, href }: { post: Post; href: string }) {
  const isAdmin = useCan()("organization.write");
  const remove = useDeletePost();
  const busy = post.generation?.status === "queued" || post.generation?.status === "running";
  const failed = post.generation?.status === "failed" && !post.current_version;
  return (
    <li className="relative grid gap-1.5 rounded-lg border p-3 transition-colors hover:bg-muted/40">
      <div className="flex items-center gap-2">
        <PlatformTag platform={post.platform} />
        <Link
          href={href}
          className="min-w-0 flex-1 truncate font-medium after:absolute after:inset-0 focus-visible:outline-none focus-visible:after:rounded-lg focus-visible:after:ring-2 focus-visible:after:ring-ring"
        >
          {post.title ?? "Untitled post"}
        </Link>
        {post.variant_of_id && <Tag tone="neutral">Variant</Tag>}
        <ChevronRightIcon aria-hidden className="size-4 shrink-0 text-muted-foreground" />
      </div>
      {busy ? (
        <p className="flex items-center gap-2 text-sm text-muted-foreground" role="status">
          <LoaderCircleIcon className="size-4 animate-spin text-primary" />
          Writing…
        </p>
      ) : failed ? (
        <p className="text-sm text-destructive">Writing failed. Open the post to try again.</p>
      ) : (
        post.hook && <p className="line-clamp-1 text-sm text-muted-foreground">{post.hook}</p>
      )}
      <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
        <Tag tone={POST_STATUS_TONE[post.status]} dot className="h-6 px-2.5 text-xs font-semibold">
          {POST_STATUS_LABEL[post.status]}
        </Tag>
        <span>
          {post.current_version ? `Version ${post.current_version} · ` : ""}
          <time dateTime={post.updated_at} title={formatDateTime(post.updated_at)}>
            Updated {timeAgo(post.updated_at)}
          </time>
        </span>
        {isAdmin && (
          <span className="relative z-10 ml-auto">
            <DeleteButton
              title={`Delete “${post.title ?? "this post"}”?`}
              description={POST_DESCRIPTION}
              pending={remove.isPending}
              onConfirm={() =>
                remove.mutate(post.id, {
                  onSuccess: () => toast.success("Post deleted"),
                  onError: (e) => toast.error(errorMessage(e)),
                })
              }
            />
          </span>
        )}
      </p>
    </li>
  );
}

/** Icon tile, title, one-line purpose and a count: the header of the plan and post cards. */
function SectionHeader({
  icon: Icon,
  title,
  description,
  badge,
  actions,
}: {
  icon: LucideIcon;
  title: string;
  description: string;
  badge: string;
  actions?: React.ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-start gap-3">
      <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-muted" aria-hidden>
        <Icon className="size-5 text-foreground" />
      </span>
      <div className="grid min-w-0 flex-1 gap-0.5">
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </div>
      <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">{badge}</span>
      {actions && (
        <div className="flex basis-full flex-wrap justify-end gap-2 sm:basis-auto">{actions}</div>
      )}
    </div>
  );
}

function PlatformFitCard({
  fit,
  recommended,
  canPlan,
  onPlan,
}: {
  fit: PlatformFit[];
  recommended: Platform[];
  canPlan: boolean;
  onPlan: (platform: Platform) => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Recommended platforms</CardTitle>
        <CardDescription>
          Scored against your audience, goals, the suggested post ideas and
          where it&apos;s trending.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        {fit.length === 0 && (
          <p className="text-sm text-muted-foreground">
            Recommendations appear after analysis.
          </p>
        )}
        {fit.map((f) => {
          const isRecommended = recommended.includes(f.platform);
          return (
            <section
              key={f.platform}
              aria-label={PLATFORM_LABEL[f.platform]}
              className="grid gap-1.5"
            >
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-medium">
                  {PLATFORM_LABEL[f.platform]}
                </h3>
                {isRecommended && (
                  <span
                    className="inline-flex items-center gap-1 text-xs text-primary-strong"
                    title="One of the best-scoring platforms for this trend."
                  >
                    <CheckCircle2Icon className="size-3.5" />
                    Recommended
                  </span>
                )}
                <span className="ml-auto text-xs tabular-nums text-muted-foreground">
                  {f.score}/100
                </span>
              </div>
              <div
                className="h-1.5 overflow-hidden rounded-full bg-muted"
                role="meter"
                aria-label={`${PLATFORM_LABEL[f.platform]} fit`}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={f.score}
              >
                <div
                  className={cn(
                    "h-full rounded-full",
                    isRecommended
                      ? "bg-foreground/60"
                      : "bg-muted-foreground/25",
                  )}
                  style={{ width: `${f.score}%` }}
                />
              </div>
              <ul className="grid gap-0.5 text-xs text-muted-foreground">
                {f.reasons.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
              {f.formats.length > 0 && (
                <p className="text-xs">
                  <span className="text-muted-foreground">Formats: </span>
                  {f.formats.join(", ")}
                </p>
              )}
              {canPlan && (
                <Button
                  size="sm"
                  variant="outline"
                  className="justify-self-start"
                  onClick={() => onPlan(f.platform)}
                >
                  Plan for {PLATFORM_LABEL[f.platform]}
                </Button>
              )}
            </section>
          );
        })}
      </CardContent>
    </Card>
  );
}

