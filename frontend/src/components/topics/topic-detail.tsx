"use client";

import {
  ArrowLeftIcon,
  CheckCircle2Icon,
  ChevronDownIcon,
  PencilIcon,
  PlusIcon,
  ShieldAlertIcon,
} from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { TOPIC_STATUS_TONE } from "@/lib/tones";
import { Tag } from "@/components/shared/tag";
import { PostRow } from "@/components/content/content-list";
import { EditTopicDialog } from "@/components/topics/edit-topic-dialog";
import { StrategyCard } from "@/components/topics/strategy-card";
import { StrategyDialog } from "@/components/topics/strategy-dialog";
import { TopicActions } from "@/components/topics/topic-actions";
import { AlignmentPanel } from "@/components/trends/alignment-panel";
import { RelevanceBadge } from "@/components/trends/relevance";
import { Score, SignalBreakdown } from "@/components/trends/score";
import { groupBySource, MentionItem } from "@/components/trends/trend-detail";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { usePosts } from "@/hooks/use-content";
import { useTopic } from "@/hooks/use-topics";
import { useMarkets } from "@/hooks/use-trends";
import { ApiError, errorMessage } from "@/lib/api";
import { useCan } from "@/lib/auth";
import { formatDateTime, stripCitations, timeAgo } from "@/lib/format";
import { PLATFORM_LABEL, TOPIC_STATUS_LABEL } from "@/lib/topics";
import { marketLabel, sourceName } from "@/lib/trends";
import { cn } from "@/lib/utils";
import type {
  ContentAngle,
  Platform,
  PlatformFit,
  Strategy,
  TopicDetail,
} from "@/types/api";

export function TopicDetailView({ id }: { id: string }) {
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
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [editing, setEditing] = useState(false);

  const back = (
    <Link
      href="/topics"
      className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
    >
      <ArrowLeftIcon className="size-4" />
      Topics
    </Link>
  );

  if (topic.isError) {
    const notFound =
      topic.error instanceof ApiError && topic.error.status === 404;
    return (
      <>
        {back}
        <Alert variant="destructive">
          <AlertDescription>
            {notFound
              ? "This topic doesn't exist or isn't in your organization."
              : errorMessage(topic.error)}
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
          {t.summary && (
            <p className="max-w-3xl text-sm text-muted-foreground">
              {t.summary}
            </p>
          )}
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
                  <CardTitle>Relevance to your organization</CardTitle>
                </CardHeader>
                <CardContent className="text-sm">
                  {stripCitations(t.relevance_reason)}
                </CardContent>
              </Card>
            )
          )}
          {trend && (
            <Card>
              <CardHeader>
                <CardTitle>Why it&apos;s trending</CardTitle>
                <CardDescription>
                  The signals behind the opportunity score.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <SignalBreakdown signals={trend.signals} />
              </CardContent>
            </Card>
          )}
          {trend && trend.mentions.length > 0 && (
            <Card>
              <CardHeader>
                <button
                  type="button"
                  aria-expanded={sourcesOpen}
                  aria-controls="topic-sources"
                  onClick={() => setSourcesOpen((o) => !o)}
                  className="flex w-full items-start gap-2 text-left"
                >
                  <span className="grid flex-1 gap-1">
                    <CardTitle>Sources ({trend.mentions.length})</CardTitle>
                    <CardDescription>
                      Where this topic is being discussed.
                    </CardDescription>
                  </span>
                  <ChevronDownIcon
                    className={cn(
                      "mt-1 size-4 shrink-0 text-muted-foreground transition-transform",
                      sourcesOpen && "rotate-180",
                    )}
                  />
                </button>
              </CardHeader>
              {sourcesOpen && (
                <CardContent id="topic-sources" className="grid gap-6">
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
                    </section>
                  ))}
                  <Link
                    href={`/trends/${trend.id}`}
                    className="text-sm underline-offset-4 hover:underline"
                  >
                    See the full trend
                  </Link>
                </CardContent>
              )}
            </Card>
          )}
        </div>

        <div className="grid content-start gap-6">
          <PlatformFitCard
            fit={t.platform_fit}
            recommended={t.recommended_platforms}
            canPlan={canManage && shortlisted}
            onPlan={plan}
          />
          {/* With a trend, the alignment panel already lists these. */}
          {!trend && t.unsupported_claims.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <ShieldAlertIcon className="size-4 text-amber-600 dark:text-amber-400" />
                  Claims to avoid
                </CardTitle>
                <CardDescription>
                  Your knowledge base doesn&apos;t support these. Keep them out
                  of the content.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <ul className="grid list-disc gap-1 pl-5 text-sm">
                  {t.unsupported_claims.map((c) => (
                    <li key={c}>{c}</li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}
          <Card>
            <CardHeader>
              <CardTitle>Details</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-4">
              <dl className="grid gap-3 text-sm">
                {t.target_audience && (
                  <Detail label="Audience" value={t.target_audience} />
                )}
                {trend && (
                  <Detail
                    label="Locations"
                    value={trend.locations
                      .map((c) => marketLabel(c, marketNames))
                      .join(", ")}
                  />
                )}
                {trend && (
                  <Detail
                    label="Last seen"
                    value={
                      <time title={formatDateTime(trend.last_seen_at)}>
                        {timeAgo(trend.last_seen_at)}
                      </time>
                    }
                  />
                )}
                <Detail
                  label="Added"
                  value={
                    <time title={formatDateTime(t.created_at)}>
                      {timeAgo(t.created_at)}
                    </time>
                  }
                />
                {t.reviewed_at && (
                  <Detail
                    label="Last decision"
                    value={
                      <time title={formatDateTime(t.reviewed_at)}>
                        {timeAgo(t.reviewed_at)}
                      </time>
                    }
                  />
                )}
              </dl>
              {trend && trend.keywords.length > 0 && (
                <div className="grid gap-2">
                  <p className="text-xs text-muted-foreground">
                    Related keywords
                  </p>
                  <ul className="flex flex-wrap gap-1.5">
                    {trend.keywords.map((k) => (
                      <li key={k}>
                        <Badge variant="outline">{k}</Badge>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      <StrategyDialog
        topic={t}
        open={!!dialog}
        platform={dialog?.platform ?? null}
        editing={dialog?.editing ?? null}
        angle={dialog?.angle ?? null}
        onClose={() => setDialog(null)}
      />
      <EditTopicDialog
        topic={t}
        open={editing}
        onClose={() => setEditing(false)}
      />
    </>
  );
}

function StrategiesCard({
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
  const postFor = (strategyId: string) => {
    const written = (posts.data?.items ?? []).filter(
      (p) => p.content_strategy_id === strategyId,
    );
    return written.find((p) => !p.variant_of_id) ?? written[0];
  };
  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-start gap-2">
        <div className="grid flex-1 gap-1">
          <CardTitle>Post plans</CardTitle>
          <CardDescription>
            {shortlisted
              ? "One plan per platform: what to say, to whom and how. Write the post straight from the plan."
              : "Shortlist this topic to plan posts for it."}
          </CardDescription>
        </div>
        {canManage && shortlisted && (
          <Button size="sm" onClick={() => onPlan(null)}>
            <PlusIcon />
            New plan
          </Button>
        )}
      </CardHeader>
      <CardContent className="grid gap-3">
        {strategies.length ? (
          strategies.map((s) => (
            <StrategyCard
              key={s.id}
              strategy={s}
              post={postFor(s.id)}
              canManage={canManage && shortlisted}
              onEdit={() => onEdit(s)}
            />
          ))
        ) : (
          <p className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
            {shortlisted
              ? "No plans yet. Pick a recommended platform on the right, or click New plan."
              : "Plans can be made once the topic is shortlisted."}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function TopicPosts({ topicId }: { topicId: string }) {
  const posts = usePosts({ status: "all", platform: "", topicId, q: "" }, 50);
  if (!posts.data?.items.length) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Posts</CardTitle>
        <CardDescription>
          Content written for this topic. Open one to edit it in the studio.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="grid gap-2" aria-label="Topic posts">
          {posts.data.items.map((p) => (
            <PostRow key={p.id} post={p} compact />
          ))}
        </ul>
      </CardContent>
    </Card>
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
          Scored against your audience, goals, the suggested angles and where
          it&apos;s trending.
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
                  <span className="inline-flex items-center gap-1 text-xs text-primary-strong">
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
                aria-hidden
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

function Detail({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="text-right">{value}</dd>
    </div>
  );
}
