"use client";

import { PencilIcon } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { TOPIC_STATUS_TONE } from "@/lib/tones";
import { BackLink, useFromHere } from "@/components/shared/back-link";
import { CollapsibleCard } from "@/components/shared/collapsible-card";
import { PageLoading } from "@/components/shared/loading";
import { Tag } from "@/components/shared/tag";
import { EditTopicDialog } from "@/components/topics/edit-topic-dialog";
import { StrategyDialog } from "@/components/topics/strategy-dialog";
import { TopicActions } from "@/components/topics/topic-actions";
import { AlignmentPanel } from "@/components/trends/alignment-panel";
import { RelevanceBadge } from "@/components/trends/relevance";
import { Score, SignalBreakdown } from "@/components/trends/score";
import { groupBySource, MentionItem } from "@/components/trends/mentions";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useTopicPosts } from "@/hooks/use-content";
import { useTopic } from "@/hooks/use-topics";
import { useMarkets } from "@/hooks/use-trends";
import { ApiError, errorMessage } from "@/lib/api";
import { useCan } from "@/lib/auth";
import { stripCitations } from "@/lib/format";
import { TOPIC_STATUS_LABEL } from "@/lib/topics";
import { sourceName } from "@/lib/trends";
import type { ContentAngle, Platform, Strategy } from "@/types/api";

import { StrategiesCard } from "./strategies-card";
import { TopicPosts } from "./topic-posts";
import { PlatformFitCard } from "./platform-fit-card";

export function TopicDetailView({ id }: { id: string }) {
  const fromHere = useFromHere();
  const topic = useTopic(id);
  // Fetched together with the topic rather than after it, so the plans don't wait twice.
  useTopicPosts(id);
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
        <PageLoading label="Loading trend…" />
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
