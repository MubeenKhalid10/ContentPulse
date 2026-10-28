"use client";

import { useQueryClient } from "@tanstack/react-query";
import { ArrowRightIcon, ArrowUpIcon, CheckIcon, MinusIcon, SparklesIcon } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { Tag } from "@/components/shared/tag";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useOrgId } from "@/hooks/use-organization";
import { useTrendAction } from "@/hooks/use-trends";
import { withFrom } from "@/lib/back";
import { errorMessage } from "@/lib/api";
import { useCan } from "@/lib/auth";
import { RELEVANCE_TONE } from "@/lib/tones";
import { sourceName } from "@/lib/trends";
import { cn } from "@/lib/utils";
import type { DashboardOverview, DashboardTrendingTopic } from "@/types/api";

import type { RelevanceFilter } from "./dashboard";

const RELEVANCE_FILTERS: { value: RelevanceFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "high", label: "High relevance" },
  { value: "medium", label: "Medium relevance" },
  { value: "low", label: "Low relevance" },
];

function matches(topic: DashboardTrendingTopic, filter: RelevanceFilter) {
  if (filter === "all") return true;
  if (filter === "high") return topic.relevance_level === "highly_relevant";
  if (filter === "medium") return topic.relevance_level === "relevant";
  return (
    topic.relevance_level !== "highly_relevant" &&
    topic.relevance_level !== "relevant"
  );
}

const RELEVANCE_LABEL: Record<string, string> = {
  highly_relevant: "Highly relevant",
  relevant: "Relevant",
  weakly_relevant: "Weakly relevant",
  not_relevant: "Not relevant",
};

export function TrendingTopics({ data }: { data?: DashboardOverview }) {
  const [filter, setFilter] = useState<RelevanceFilter>("all");
  const rows = (data?.trending ?? []).filter((t) => matches(t, filter));
  const shown = rows.slice(0, 6);
  return (
    <Card>
      <CardHeader className="gap-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="grid gap-1">
            <CardTitle>Trending topics</CardTitle>
            <CardDescription>
              What&apos;s gaining attention in your markets, and how relevant it
              is to you.
            </CardDescription>
          </div>
          <Link
            href="/trends"
            className={buttonVariants({ variant: "outline", size: "sm" })}
          >
            View all trends <ArrowRightIcon />
          </Link>
        </div>
        <div
          role="group"
          aria-label="Filter by relevance"
          className="flex flex-wrap gap-1.5"
        >
          {RELEVANCE_FILTERS.map((f) => (
            <button
              key={f.value}
              type="button"
              aria-pressed={filter === f.value}
              onClick={() => setFilter(f.value)}
              className={cn(
                "h-8 rounded-md border px-3 text-xs font-medium transition-colors outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
                filter === f.value
                  ? "border-foreground bg-foreground text-background"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground",
              )}
            >
              {f.label}
            </button>
          ))}
        </div>
      </CardHeader>
      <CardContent>
        {!data ? (
          <Skeleton className="h-48 w-full" />
        ) : shown.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">
            {data.trending.length
              ? "No trends at this relevance in this period."
              : <>No trends collected in this period yet. Run discovery on the{" "}
                  <Link href="/trends" className="underline underline-offset-4">Trends page</Link>.</>}
          </p>
        ) : (
          <div className="-mx-4 overflow-x-auto px-4">
            <table className="w-full min-w-[46rem] text-sm">
              <thead>
                <tr className="border-b text-left text-xs text-muted-foreground">
                  <th scope="col" className="py-2 pr-3 font-medium">
                    Topic
                  </th>
                  <th scope="col" className="py-2 pr-3 font-medium">
                    Source
                  </th>
                  <th scope="col" className="py-2 pr-3 font-medium">
                    Category
                  </th>
                  <th
                    scope="col"
                    className="py-2 pr-3 font-medium"
                    title="Opportunity score, 0 to 100"
                  >
                    Opportunity score
                    <span className="block text-[11px] font-normal">0–100</span>
                  </th>
                  <th
                    scope="col"
                    className="py-2 pr-3 font-medium"
                    title="How fast attention is growing, 0-100"
                  >
                    Momentum
                  </th>
                  <th scope="col" className="py-2 pr-3 font-medium">
                    Why it matters
                  </th>
                  <th scope="col" className="py-2 font-medium">
                    <span className="sr-only">Action</span>
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {shown.map((t) => (
                  <TrendingRow key={t.id} topic={t} />
                ))}
              </tbody>
            </table>
          </div>
        )}
        {data && rows.length > 0 && (
          <p className="mt-3 text-xs text-muted-foreground">
            Showing {shown.length} of {rows.length} trends in this period.
            Opportunity score shows how well a trend fits your organization;
            momentum shows how fast attention is growing (both 0–100).
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function TrendingRow({ topic: t }: { topic: DashboardTrendingTopic }) {
  const can = useCan();
  const action = useTrendAction();
  const queryClient = useQueryClient();
  const orgId = useOrgId();
  const canShortlist = can("trends.manage") || can("topics.manage");
  return (
    <tr className="align-middle">
      <td className="max-w-56 py-2.5 pr-3">
        <Link
          href={withFrom(`/trends/${t.id}`, "/dashboard")}
          className="font-medium underline-offset-4 hover:underline"
        >
          {t.topic}
        </Link>
      </td>
      <td className="py-2.5 pr-3 whitespace-nowrap text-muted-foreground">
        {t.source ? sourceName(t.source) : "—"}
      </td>
      <td className="py-2.5 pr-3">
        {t.category ? (
          <Tag tone="neutral">{t.category}</Tag>
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </td>
      <td className="py-2.5 pr-3">
        {t.opportunity_score != null ? (
          <Tag
            tone={
              t.relevance_level ? RELEVANCE_TONE[t.relevance_level] : "neutral"
            }
            title={
              t.relevance_level
                ? RELEVANCE_LABEL[t.relevance_level]
                : "Not analysed yet"
            }
            className="tabular-nums"
          >
            {t.relevance_level && (
              <span className="sr-only">
                {RELEVANCE_LABEL[t.relevance_level]}:{" "}
              </span>
            )}
            {Math.round(t.opportunity_score)}
          </Tag>
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </td>
      <td className="py-2.5 pr-3 whitespace-nowrap tabular-nums">
        {t.momentum != null ? (
          <span className="inline-flex items-center gap-1">
            {t.momentum >= 50 ? (
              <ArrowUpIcon className="size-3 text-success" aria-hidden />
            ) : (
              <MinusIcon className="size-3 text-muted-foreground" aria-hidden />
            )}
            {t.momentum}
            <span className="text-xs text-muted-foreground">/100</span>
          </span>
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </td>
      <td className="max-w-64 py-2.5 pr-3 text-muted-foreground">
        <span className="line-clamp-1" title={t.why ?? undefined}>
          {t.why ?? "Not analysed yet."}
        </span>
      </td>
      <td className="py-2.5 text-right whitespace-nowrap">
        {t.shortlisted ? (
          <span className="inline-flex items-center gap-1 text-sm text-muted-foreground">
            <CheckIcon className="size-4 text-success" aria-hidden /> Shortlisted
          </span>
        ) : !canShortlist ? (
          <Link
            href={withFrom(`/trends/${t.id}`, "/dashboard")}
            className={buttonVariants({ variant: "outline", size: "sm" })}
          >
            Open
          </Link>
        ) : (
          <Button
            variant="outline"
            size="sm"
            disabled={action.isPending && action.variables?.id === t.id}
            aria-label={`Shortlist ${t.topic}`}
            onClick={() =>
              action.mutate(
                { id: t.id, action: "shortlist" },
                {
                  onSuccess: () => {
                    toast.success(
                      `Shortlisted “${t.topic}”. Plan a post from Shortlist & plans.`,
                    );
                    queryClient.invalidateQueries({
                      queryKey: ["org", orgId, "dashboard"],
                    });
                  },
                  onError: (e) => toast.error(errorMessage(e)),
                },
              )
            }
          >
            <SparklesIcon /> Shortlist
          </Button>
        )}
      </td>
    </tr>
  );
}

// --- Content pipeline ----------------------------------------------------------------
