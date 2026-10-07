"use client";

import { ListChecksIcon } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Tag } from "@/components/shared/tag";
import { PageHeader } from "@/components/shared/page-header";
import { SimpleSelect } from "@/components/shared/simple-select";
import { PlatformBadges } from "@/components/topics/platform-badges";
import { TopicActions } from "@/components/topics/topic-actions";
import { RelevanceBadge } from "@/components/trends/relevance";
import { Score } from "@/components/trends/score";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { type TopicFilters, type TopicStatusFilter, useTopics } from "@/hooks/use-topics";
import { useCan } from "@/lib/auth";
import { PLATFORM_OPTIONS } from "@/lib/options";
import { cn } from "@/lib/utils";
import type { Topic, TopicPage } from "@/types/api";

const PAGE = 30;
const RELEVANCE_FILTERS = [
  { value: "all", label: "Any relevance" },
  { value: "relevant", label: "Relevant to us" },
  { value: "highly_relevant", label: "Highly relevant" },
  { value: "weakly_relevant", label: "Weakly relevant" },
  { value: "not_relevant", label: "Not relevant" },
];
const PLATFORM_FILTERS = [{ value: "all", label: "Any platform" }, ...PLATFORM_OPTIONS];
const SORTS = [
  { value: "score", label: "Best opportunity" },
  { value: "relevance", label: "Most relevant" },
  { value: "recent", label: "Newest" },
] as const;
const TABS: { value: TopicStatusFilter; label: string; count: (c: TopicPage["counts"]) => number }[] = [
  { value: "open", label: "To review", count: (c) => c.new + c.reviewed },
  { value: "shortlisted", label: "Shortlisted", count: (c) => c.shortlisted },
  { value: "rejected", label: "Rejected", count: (c) => c.rejected },
  { value: "archived", label: "Archived", count: (c) => c.archived },
];
const EMPTY: Record<TopicStatusFilter, string> = {
  open: "Nothing waiting for review. New topics appear here after trends are analyzed.",
  shortlisted: "No shortlisted topics yet. Shortlist a topic to plan content for it.",
  rejected: "No rejected topics.",
  archived: "No archived topics.",
  all: "No topics yet.",
};

export function TopicsExplorer() {
  const canManage = useCan()("topics.manage");
  const [filters, setFilters] = useState<TopicFilters>({
    status: "open",
    relevance: "",
    platform: "",
    sort: "score",
    q: "",
  });
  const [limit, setLimit] = useState(PAGE);
  const topics = useTopics(filters, limit);
  const update = (patch: Partial<TopicFilters>) => {
    setFilters((f) => ({ ...f, ...patch }));
    setLimit(PAGE);
  };
  const counts = topics.data?.counts;
  const noTopicsAtAll =
    counts && Object.values(counts).every((n) => n === 0) && !filters.q && !filters.platform && !filters.relevance;

  return (
    <>
      <PageHeader
        title="Topics"
        description="Trends that fit your organization. Shortlist the ones worth posting about, then plan a post for each platform."
      />

      {noTopicsAtAll ? (
        <Card>
          <CardContent className="grid justify-items-center gap-4 py-12 text-center">
            <span className="grid size-12 place-items-center rounded-full bg-muted">
              <ListChecksIcon className="size-6 text-muted-foreground" />
            </span>
            <div className="grid max-w-md gap-1.5">
              <p className="text-lg font-medium">No topic candidates yet</p>
              <p className="text-sm text-muted-foreground">
                When analysis finds a trend relevant to your organization, it becomes a topic here. You can
                also shortlist any trend from the Trends page.
              </p>
            </div>
            <Link href="/trends" className={buttonVariants({ variant: "outline" })}>
              Go to Trends
            </Link>
          </CardContent>
        </Card>
      ) : (
        <div className="grid min-w-0 grid-cols-1 gap-6">
          <div className="flex flex-wrap items-center gap-3">
            <Tabs value={filters.status} onValueChange={(v) => update({ status: v as TopicStatusFilter })}>
              <TabsList>
                {TABS.map((tab) => (
                  <TabsTrigger key={tab.value} value={tab.value}>
                    {tab.label}
                    {counts && tab.count(counts) > 0 && (
                      <span className="ml-1 rounded-full bg-muted px-1.5 text-[11px] tabular-nums text-muted-foreground">
                        {tab.count(counts)}
                      </span>
                    )}
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>
            <Input
              aria-label="Search topics"
              placeholder="Search topics"
              value={filters.q}
              onChange={(e) => update({ q: e.target.value })}
              className="w-full sm:w-56"
            />
            <div className="flex flex-wrap gap-2 sm:ml-auto">
              <SimpleSelect
                aria-label="Relevance"
                value={filters.relevance || "all"}
                onChange={(v) => update({ relevance: v === "all" ? "" : (v as TopicFilters["relevance"]) })}
                options={RELEVANCE_FILTERS}
                className="w-44"
              />
              <SimpleSelect
                aria-label="Platform"
                value={filters.platform || "all"}
                onChange={(v) => update({ platform: v === "all" ? "" : (v as TopicFilters["platform"]) })}
                options={PLATFORM_FILTERS}
                className="w-40"
              />
              <SimpleSelect
                aria-label="Sort by"
                value={filters.sort}
                onChange={(v) => update({ sort: v })}
                options={SORTS}
                className="w-44"
              />
            </div>
          </div>

          {topics.isPending ? (
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
              {filters.q || filters.platform || filters.relevance ? "No topics match these filters." : EMPTY[filters.status]}
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
            href={`/topics/${topic.id}`}
            className="max-w-full truncate text-base font-medium after:absolute after:inset-0 focus-visible:outline-none focus-visible:after:rounded-xl focus-visible:after:ring-2 focus-visible:after:ring-ring"
          >
            {topic.title}
          </Link>
          <RelevanceBadge level={topic.relevance_level} />
          {topic.status === "reviewed" && <Tag tone="sky" dot>Reviewed</Tag>}
        </div>
        {topic.summary && <p className="line-clamp-1 text-sm text-muted-foreground">{topic.summary}</p>}
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs text-muted-foreground">
          <PlatformBadges platforms={topic.recommended_platforms} />
          {topic.matched_services.length > 0 && <span>Services: {topic.matched_services.join(", ")}</span>}
          {topic.strategy_count > 0 && (
            <span>
              {topic.strategy_count} {topic.strategy_count === 1 ? "plan" : "plans"}
              {topic.approved_strategy_count > 0 && ` · ${topic.approved_strategy_count} written`}
            </span>
          )}
        </div>
      </div>
      {canManage && (
        <div className="relative z-10 flex basis-full items-center pl-16 sm:basis-auto sm:self-center sm:pl-0">
          <TopicActions topic={topic} compact />
        </div>
      )}
    </li>
  );
}
