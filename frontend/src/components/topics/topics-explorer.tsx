"use client";

import { ListChecksIcon } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { PageHeader } from "@/components/shared/page-header";
import {
  FILTER_SEARCH,
  FILTER_SELECT,
  FilterBar,
} from "@/components/shared/filter-bar";
import { SearchInput } from "@/components/shared/search-input";
import { SimpleSelect } from "@/components/shared/simple-select";
import { PlatformBadges } from "@/components/topics/platform-badges";
import { TopicActions } from "@/components/topics/topic-actions";
import { RelevanceBadge } from "@/components/trends/relevance";
import { Score } from "@/components/trends/score";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { usePersistedState } from "@/hooks/use-persisted-state";
import { type TopicFilters, useTopics } from "@/hooks/use-topics";
import { errorMessage } from "@/lib/api";
import { useCan } from "@/lib/auth";
import { PLATFORM_OPTIONS } from "@/lib/options";
import { topicHref } from "@/lib/topics";
import { cn } from "@/lib/utils";
import type { Topic } from "@/types/api";

const PAGE = 30;
const PLATFORM_FILTERS = [{ value: "all", label: "Any platform" }, ...PLATFORM_OPTIONS];
const SORTS = [
  { value: "score", label: "Best opportunity" },
  { value: "recent", label: "Newest" },
] as const;
export function TopicsExplorer() {
  const canManage = useCan()("topics.manage");
  const [saved, setFilters] = usePersistedState<TopicFilters>("topics", {
    status: "shortlisted",
    relevance: "",
    platform: "",
    sort: "score",
    q: "",
  });
  // This page lists shortlisted trends only; new trends are reviewed on Find trends.
  const filters: TopicFilters = { ...saved, status: "shortlisted", relevance: "" };
  const [limit, setLimit] = useState(PAGE);
  const topics = useTopics(filters, limit);
  const update = (patch: Partial<TopicFilters>) => {
    setFilters((f) => ({ ...f, ...patch }));
    setLimit(PAGE);
  };
  const counts = topics.data?.counts;
  const noTopicsAtAll = counts && counts.shortlisted === 0 && !filters.q && !filters.platform;

  return (
    <>
      <PageHeader
        title="Shortlist & plans"
        description="The trends you shortlisted, with a post plan and posts for each platform. New trends are reviewed on Find trends."
      />

      {noTopicsAtAll ? (
        <Card>
          <CardContent className="grid justify-items-center gap-4 py-12 text-center">
            <span className="grid size-12 place-items-center rounded-full bg-muted">
              <ListChecksIcon className="size-6 text-muted-foreground" />
            </span>
            <div className="grid max-w-md gap-1.5">
              <p className="text-lg font-medium">Nothing shortlisted yet</p>
              <p className="text-sm text-muted-foreground">
                Relevant trends are reviewed on Find trends. Shortlist one there and its post plans
                and posts appear here.
              </p>
            </div>
            <Link href="/trends" className={buttonVariants({ variant: "outline" })}>
              Go to Find trends
            </Link>
          </CardContent>
        </Card>
      ) : (
        <div className="grid min-w-0 grid-cols-1 gap-6">
          <FilterBar>
            <SearchInput
              aria-label="Search shortlisted trends"
              placeholder="Search shortlisted trends"
              value={filters.q}
              onChange={(q) => update({ q })}
              className={FILTER_SEARCH}
            />
            <SimpleSelect
              aria-label="Platform"
              value={filters.platform || "all"}
              onChange={(v) => update({ platform: v === "all" ? "" : (v as TopicFilters["platform"]) })}
              options={PLATFORM_FILTERS}
              className={FILTER_SELECT}
            />
            <SimpleSelect
              aria-label="Sort by"
              value={filters.sort}
              onChange={(v) => update({ sort: v })}
              options={SORTS}
              className={FILTER_SELECT}
            />
          </FilterBar>

          {topics.isError ? (
            <div
              role="alert"
              className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-destructive/40 p-4 text-sm"
            >
              <span className="text-destructive">
                Couldn&apos;t load your shortlist. {errorMessage(topics.error)}
              </span>
              <Button variant="outline" size="sm" onClick={() => topics.refetch()}>
                Retry
              </Button>
            </div>
          ) : topics.isPending ? (
            <div className="grid gap-3">
              {Array.from({ length: 4 }, (_, i) => (
                <Skeleton key={i} className="h-24 w-full rounded-xl" />
              ))}
            </div>
          ) : topics.data?.items.length ? (
            <>
              <ul
                className={cn("grid min-w-0 grid-cols-1 gap-3 transition-opacity", topics.isPlaceholderData && "opacity-50")}
                aria-label="Topics"
                aria-busy={topics.isPlaceholderData}
              >
                {topics.data.items.map((topic) => (
                  <TopicRow key={topic.id} topic={topic} canManage={canManage} />
                ))}
              </ul>
              {topics.data.total > topics.data.items.length && (
                <Button variant="outline" className="justify-self-center" onClick={() => setLimit((n) => n + PAGE)}>
                  Show more ({topics.data.total - topics.data.items.length} left)
                </Button>
              )}
            </>
          ) : (
            <p className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">
              {filters.q || filters.platform ? "No shortlisted trends match these filters." : "Nothing shortlisted yet. Shortlist a trend on Find trends to plan posts for it here."}
            </p>
          )}
        </div>
      )}
    </>
  );
}

function TopicRow({ topic, canManage }: { topic: Topic; canManage: boolean }) {
  return (
    <li className="group relative flex flex-wrap items-start gap-x-4 gap-y-3 rounded-xl bg-card p-4 ring-1 ring-foreground/10 transition-colors hover:bg-muted/40 sm:flex-nowrap">
      <Score score={topic.opportunity_score} />
      <div className="grid min-w-0 flex-1 grid-cols-1 gap-1.5">
        <div className="flex flex-wrap items-center gap-2">
          <Link
            href={topicHref(topic)}
            className="line-clamp-2 max-w-full text-base font-medium after:absolute after:inset-0 focus-visible:outline-none focus-visible:after:rounded-xl focus-visible:after:ring-2 focus-visible:after:ring-ring"
          >
            {topic.title}
          </Link>
          <RelevanceBadge level={topic.relevance_level} />
        </div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs text-muted-foreground">
          <PlatformBadges platforms={topic.recommended_platforms} />
          {topic.matched_services.length > 0 && <span>Services: {topic.matched_services.join(", ")}</span>}
          {topic.strategy_count > 0 && (
            <span>
              {topic.strategy_count} {topic.strategy_count === 1 ? "plan" : "plans"}
              {topic.approved_strategy_count > 0 && ` · ${topic.approved_strategy_count} posts written`}
            </span>
          )}
        </div>
      </div>
      <div className="relative z-10 flex basis-full flex-wrap items-center gap-1.5 pl-16 sm:basis-auto sm:self-center sm:pl-0">
        <Link
          href={topicHref(topic)}
          aria-label={`View trend ${topic.title}`}
          className={buttonVariants({ variant: "view", size: "sm" })}
        >
          View trend
        </Link>
        {canManage && <TopicActions topic={topic} compact />}
      </div>
    </li>
  );
}
