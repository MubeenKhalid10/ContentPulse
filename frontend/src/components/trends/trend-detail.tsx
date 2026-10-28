"use client";

import { NewspaperIcon } from "lucide-react";
import { useMemo, useState } from "react";

import { TREND_STATUS_TONE } from "@/lib/tones";
import { BackLink } from "@/components/shared/back-link";
import { Tag } from "@/components/shared/tag";
import { AlignmentPanel } from "@/components/trends/alignment-panel";
import { RelevanceBadge } from "@/components/trends/relevance";
import { CollapsibleCard } from "@/components/shared/collapsible-card";
import { Score, SignalBreakdown } from "@/components/trends/score";
import { TrendActions } from "@/components/trends/trend-row";
import { StrategyDialog } from "@/components/topics/strategy-dialog";
import { StrategiesCard } from "@/components/topics/strategies-card";
import { TopicPosts } from "@/components/topics/topic-posts";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useTopic } from "@/hooks/use-topics";
import { useMarkets, useTrend } from "@/hooks/use-trends";
import { ApiError, errorMessage } from "@/lib/api";
import { useCan } from "@/lib/auth";
import { formatDateTime, timeAgo } from "@/lib/format";
import { marketLabel, sourceName } from "@/lib/trends";
import type { ContentAngle, Platform, Strategy, TrendDetail } from "@/types/api";

const STATUS_LABEL: Record<string, string> = {
  new: "New",
  analyzed: "Analyzed",
  shortlisted: "Shortlisted",
  rejected: "Rejected",
  archived: "Archived",
};

export function TrendDetailView({ id }: { id: string }) {
  const trend = useTrend(id);
  const markets = useMarkets();
  const can = useCan();
  const canReview = can("trends.manage") || can("topics.manage");
  const marketNames = useMemo(
    () => new Map(markets.data?.map((m) => [m.code, m.name])),
    [markets.data],
  );

  const back = <BackLink href="/trends" label="Trends" />;

  if (trend.isError) {
    const notFound =
      trend.error instanceof ApiError && trend.error.status === 404;
    return (
      <>
        {back}
        <Alert variant="destructive">
          <AlertDescription className="flex flex-wrap items-center gap-3">
            <span>
              {notFound
                ? "This trend doesn't exist or isn't in your organization."
                : errorMessage(trend.error)}
            </span>
            {!notFound && (
              <Button size="sm" variant="outline" onClick={() => trend.refetch()}>
                Try again
              </Button>
            )}
          </AlertDescription>
        </Alert>
      </>
    );
  }
  if (!trend.data) {
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

  const t = trend.data;

  return (
    <>
      {back}
      <div className="mb-8 flex flex-wrap items-start gap-4">
        <Score score={t.opportunity_score} size="lg" />
        <div className="grid min-w-0 flex-1 gap-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">{t.topic}</h1>
            <Tag tone={TREND_STATUS_TONE[t.status] ?? "neutral"} dot>
              {STATUS_LABEL[t.status] ?? t.status}
            </Tag>
            <RelevanceBadge
              level={t.relevance_level}
              overridden={t.relevance_overridden}
            />
          </div>
          <p className="text-sm text-muted-foreground">
            {t.opportunity_score == null
              ? "Not scored yet"
              : `Opportunity score ${Math.round(t.opportunity_score)} of 100`}{" "}
            (how strongly it is rising across your sources) · {t.mention_count} mention{t.mention_count === 1 ? "" : "s"}{" "}
            across {t.sources.length} source
            {t.sources.length === 1 ? "" : "s"}
          </p>
          <p className="text-xs text-muted-foreground">
            {t.status === "shortlisted"
              ? "Shortlisted: plan posts for it below."
              : t.status === "rejected"
                ? "Rejected: hidden from To review. Restore it to review it again."
                : "Shortlist a trend to plan posts for it, or reject it to hide it."}
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {canReview && <TrendActions trend={t} />}
        </div>
      </div>

      <div className="grid gap-6">
        <div className="grid content-start gap-6">
          {/* Once shortlisted the page is for planning: the summary is only for deciding. */}
          {t.status !== "shortlisted" && <SummaryCard trend={t} marketNames={marketNames} />}
          {t.status === "shortlisted" && t.topic_id && can("topics.read") ? (
            <ShortlistPlans trend={t} canReview={canReview} />
          ) : (
            <AlignmentPanel trend={t} canReview={canReview} mode="fit" />
          )}
          <CollapsibleCard
            title="Why it's trending"
            description="The signals behind the opportunity score."
          >
            <SignalBreakdown signals={t.signals} />
          </CollapsibleCard>
        </div>

      </div>
    </>
  );
}

/** What the trend is, in a few lines. */
function SummaryCard({
  trend,
  marketNames,
}: {
  trend: TrendDetail;
  marketNames: Map<string, string>;
}) {
  const text = trend.description ?? trend.title ?? trend.topic;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <NewspaperIcon className="size-4 text-primary" aria-hidden />
          Summary
        </CardTitle>
      </CardHeader>
      <CardContent className="grid gap-3">
        <p className="text-sm leading-relaxed">{text}</p>
        <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
          <span>{trend.sources.map(sourceName).join(" · ")}</span>
          <span aria-hidden>•</span>
          <span>{trend.locations.map((c) => marketLabel(c, marketNames)).join(", ")}</span>
          <span aria-hidden>•</span>
          <time dateTime={trend.last_seen_at} title={formatDateTime(trend.last_seen_at)}>
            Last seen {timeAgo(trend.last_seen_at)}
          </time>
        </p>
      </CardContent>
    </Card>
  );
}

/** A shortlisted trend is planned right here: post plans and posts first, then
 * the fit analysis, whose post ideas start a plan. Same data as the topic page. */
function ShortlistPlans({
  trend,
  canReview,
}: {
  trend: TrendDetail;
  canReview: boolean;
}) {
  const topic = useTopic(trend.topic_id as string, false);
  const can = useCan();
  const canManage = can("topics.manage");
  const [dialog, setDialog] = useState<{
    platform: Platform | null;
    editing: Strategy | null;
    angle?: ContentAngle;
  } | null>(null);
  const t = topic.data;
  // "Plan post" on a list row opens this page with the plan pop-up already open.
  const [autoPlan, setAutoPlan] = useState(
    () => typeof window !== "undefined" && new URLSearchParams(window.location.search).get("plan") === "1",
  );
  return (
    <>
      {t ? (
        <>
          <StrategiesCard
            topic={t}
            canManage={canManage}
            onPlan={(platform) => setDialog({ platform, editing: null })}
            onEdit={(s) => setDialog({ platform: s.platform, editing: s })}
          />
          {can("content.read") && <TopicPosts topicId={t.id} />}
        </>
      ) : (
        topic.isError ? (
          <Alert variant="destructive">
            <AlertDescription className="flex flex-wrap items-center gap-3">
              <span>Couldn&apos;t load the post plans. {errorMessage(topic.error)}</span>
              <Button size="sm" variant="outline" onClick={() => topic.refetch()}>
                Try again
              </Button>
            </AlertDescription>
          </Alert>
        ) : (
          <Skeleton className="h-40 w-full rounded-xl" />
        )
      )}
      <AlignmentPanel
        trend={trend}
        canReview={canReview}
        mode="ideas"
        onPlanAngle={
          t && canManage
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
      {t && (
        <StrategyDialog
          topic={t}
          open={!!dialog || (autoPlan && canManage)}
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
      )}
    </>
  );
}
