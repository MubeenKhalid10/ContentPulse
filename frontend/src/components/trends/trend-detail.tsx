"use client";

import { ArrowLeftIcon, ExternalLinkIcon, ListChecksIcon } from "lucide-react";
import Link from "next/link";
import { useMemo } from "react";

import { TREND_STATUS_TONE } from "@/lib/tones";
import { Tag } from "@/components/shared/tag";
import { AlignmentPanel } from "@/components/trends/alignment-panel";
import { RelevanceBadge } from "@/components/trends/relevance";
import { Score, SignalBreakdown } from "@/components/trends/score";
import { TrendActions } from "@/components/trends/trend-row";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useMarkets, useTrend } from "@/hooks/use-trends";
import { ApiError, errorMessage } from "@/lib/api";
import { useCan } from "@/lib/auth";
import { formatDateTime, timeAgo } from "@/lib/format";
import { marketLabel, sourceName } from "@/lib/trends";
import type { TrendMention } from "@/types/api";

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
  const marketNames = useMemo(() => new Map(markets.data?.map((m) => [m.code, m.name])), [markets.data]);

  const back = (
    <Link href="/trends" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
      <ArrowLeftIcon className="size-4" />
      Trends
    </Link>
  );

  if (trend.isError) {
    const notFound = trend.error instanceof ApiError && trend.error.status === 404;
    return (
      <>
        {back}
        <Alert variant="destructive">
          <AlertDescription>{notFound ? "This trend doesn't exist or isn't in your organization." : errorMessage(trend.error)}</AlertDescription>
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
  const bySource = groupBySource(t.mentions);

  return (
    <>
      {back}
      <div className="mb-8 flex flex-wrap items-start gap-4">
        <Score score={t.opportunity_score} size="lg" />
        <div className="grid min-w-0 flex-1 gap-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">{t.topic}</h1>
            <Tag tone={TREND_STATUS_TONE[t.status] ?? "neutral"} dot>{STATUS_LABEL[t.status]}</Tag>
            <RelevanceBadge level={t.relevance_level} overridden={t.relevance_overridden} />
          </div>
          <p className="text-sm text-muted-foreground">
            Opportunity score {t.opportunity_score == null ? "—" : Math.round(t.opportunity_score)} of 100 ·{" "}
            {t.mention_count} mention{t.mention_count === 1 ? "" : "s"} across {t.sources.length} source
            {t.sources.length === 1 ? "" : "s"}
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {t.topic_id && (
            <Link href={`/topics/${t.topic_id}`} className={buttonVariants({ variant: t.status === "shortlisted" ? "default" : "outline", size: "sm" })}>
              <ListChecksIcon />
              Open topic
            </Link>
          )}
          {canReview && <TrendActions trend={t} />}
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="grid content-start gap-6 lg:col-span-2">
          <AlignmentPanel trend={t} canReview={canReview} />
          <Card>
            <CardHeader>
              <CardTitle>Why it&apos;s trending</CardTitle>
              <CardDescription>The signals behind the opportunity score.</CardDescription>
            </CardHeader>
            <CardContent>
              <SignalBreakdown signals={t.signals} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Evidence</CardTitle>
              <CardDescription>Every mention we found, with links to the original source.</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-6">
              {bySource.map(([source, mentions]) => (
                <section key={source} aria-label={sourceName(source)} className="grid gap-2">
                  <h2 className="text-sm font-medium">
                    {sourceName(source)} <span className="font-normal text-muted-foreground">({mentions.length})</span>
                  </h2>
                  <ul className="grid gap-2">
                    {mentions.slice(0, 8).map((m) => (
                      <MentionItem key={m.id} mention={m} marketNames={marketNames} />
                    ))}
                  </ul>
                  {mentions.length > 8 && (
                    <p className="text-xs text-muted-foreground">+ {mentions.length - 8} more</p>
                  )}
                </section>
              ))}
            </CardContent>
          </Card>
        </div>

        <div className="grid content-start gap-6">
          <Card>
            <CardHeader>
              <CardTitle>Details</CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="grid gap-3 text-sm">
                <Detail label="First seen" value={<time title={formatDateTime(t.first_seen_at)}>{timeAgo(t.first_seen_at)}</time>} />
                <Detail label="Last seen" value={<time title={formatDateTime(t.last_seen_at)}>{timeAgo(t.last_seen_at)}</time>} />
                <Detail label="Locations" value={t.locations.map((c) => marketLabel(c, marketNames)).join(", ")} />
                {t.category && <Detail label="Category" value={t.category} />}
              </dl>
              {t.keywords.length > 0 && (
                <div className="mt-4 grid gap-2">
                  <p className="text-xs text-muted-foreground">Related keywords</p>
                  <ul className="flex flex-wrap gap-1.5">
                    {t.keywords.map((k) => (
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
    </>
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

export function groupBySource(mentions: TrendMention[]): [string, TrendMention[]][] {
  const groups = new Map<string, TrendMention[]>();
  for (const m of mentions) groups.set(m.source, [...(groups.get(m.source) ?? []), m]);
  return [...groups.entries()];
}

export function MentionItem({ mention: m, marketNames }: { mention: TrendMention; marketNames: Map<string, string> }) {
  const when = m.published_at ?? m.detected_at;
  return (
    <li className="grid gap-0.5 rounded-lg border p-3">
      {m.source_url ? (
        <a
          href={m.source_url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-start gap-1 text-sm font-medium underline-offset-4 hover:underline"
        >
          {m.title}
          <ExternalLinkIcon className="mt-0.5 size-3 shrink-0 text-muted-foreground" />
        </a>
      ) : (
        <p className="text-sm font-medium">{m.title}</p>
      )}
      {m.description && <p className="line-clamp-2 text-xs text-muted-foreground">{m.description}</p>}
      <p className="flex flex-wrap gap-x-2 text-xs text-muted-foreground">
        {m.author && <span>{m.author}</span>}
        {m.engagement_label && <span className="font-medium text-foreground">{m.engagement_label}</span>}
        {m.location && m.location !== "GLOBAL" && <span>{marketLabel(m.location, marketNames)}</span>}
        <time dateTime={when} title={formatDateTime(when)}>
          {timeAgo(when)}
        </time>
      </p>
    </li>
  );
}
