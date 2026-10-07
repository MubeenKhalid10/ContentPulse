"use client";

import { useQueryClient } from "@tanstack/react-query";
import { RadarIcon, SettingsIcon, TrendingUpIcon } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/shared/page-header";
import { SimpleSelect } from "@/components/shared/simple-select";
import { RunStatus } from "@/components/trends/run-status";
import { TrendRow } from "@/components/trends/trend-row";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useOrgSettings, useOrgId } from "@/hooks/use-organization";
import {
  type RelevanceFilter,
  type TrendFilters,
  useAIStatus,
  useDiscover,
  useDiscoveryRuns,
  useMarkets,
  useTrendSources,
  useTrends,
} from "@/hooks/use-trends";
import { ApiError, errorMessage } from "@/lib/api";
import { useCan } from "@/lib/auth";
import { sourceName } from "@/lib/trends";
import { cn } from "@/lib/utils";

const PAGE = 30;
const RELEVANCE_FILTERS = [
  { value: "all", label: "Any relevance" },
  { value: "relevant", label: "Relevant to us" },
  { value: "highly_relevant", label: "Highly relevant" },
  { value: "weakly_relevant", label: "Weakly relevant" },
  { value: "not_relevant", label: "Not relevant" },
  { value: "unanalyzed", label: "Not analyzed yet" },
];
const SORTS = [
  { value: "score", label: "Best opportunity" },
  { value: "recent", label: "Most recent" },
  { value: "mentions", label: "Most mentioned" },
  { value: "new", label: "Newest trends" },
] as const;

export function TrendsExplorer() {
  const can = useCan();
  const canDiscover = can("trends.manage");
  const canReview = can("trends.manage") || can("topics.manage");
  const [filters, setFilters] = useState<TrendFilters>({
    status: "active",
    relevance: "",
    sort: "score",
    source: "",
    location: "",
    q: "",
  });
  const [limit, setLimit] = useState(PAGE);
  const trends = useTrends(filters, limit);
  const runs = useDiscoveryRuns();
  const sources = useTrendSources();
  const settings = useOrgSettings();
  const markets = useMarkets();
  const discover = useDiscover();
  const ai = useAIStatus();
  const latest = runs.data?.[0];
  const running = latest?.status === "queued" || latest?.status === "running";
  useRunCompletion(latest?.id, latest?.status);

  const marketNames = useMemo(() => new Map(markets.data?.map((m) => [m.code, m.name])), [markets.data]);
  const sourceOptions = [
    { value: "all", label: "All sources" },
    ...(sources.data ?? []).filter((s) => s.enabled).map((s) => ({ value: s.key, label: s.name })),
  ];
  const locationCodes = Array.from(new Set(trends.data?.items.flatMap((t) => t.locations) ?? []));
  const locationOptions = [
    { value: "all", label: "All locations" },
    ...locationCodes.map((c) => ({ value: c, label: marketNames.get(c) ?? (c === "GLOBAL" ? "Global" : c) })),
  ];

  const update = (patch: Partial<TrendFilters>) => {
    setFilters((f) => ({ ...f, ...patch }));
    setLimit(PAGE);
  };

  const noRunsYet = runs.data && runs.data.length === 0;
  const enabledCount = settings.data?.enabled_sources.length ?? 0;

  return (
    <>
      <PageHeader
        title="Trends"
        description={
          <>
            What&apos;s rising in your markets, scored for your organization. Shortlist the trends
            worth posting about.{" "}
            {ai.data && (
              <span className="sm:whitespace-nowrap">
                {ai.data.engine === "ai"
                  ? `Relevance checked by AI (${ai.data.model}).`
                  : "Relevance is a keyword-based estimate (no AI model set up)."}
              </span>
            )}
          </>
        }
        actions={
          <>
            <Link href="/trends/sources" className={buttonVariants({ variant: "outline" })}>
              <SettingsIcon />
              Sources
            </Link>
            {canDiscover && (
              <Button
                disabled={running || discover.isPending || enabledCount === 0}
                onClick={() =>
                  discover.mutate({}, { onSuccess: onDiscoverStarted, onError: onDiscoverError })
                }
              >
                <RadarIcon />
                {running ? "Discovering…" : "Discover now"}
              </Button>
            )}
          </>
        }
      />

      <div className="grid min-w-0 grid-cols-1 gap-6">
        {latest && <RunStatus run={latest} />}

        {noRunsYet ? (
          <Card>
            <CardContent className="grid justify-items-center gap-4 py-12 text-center">
              <span className="grid size-12 place-items-center rounded-full bg-muted">
                <TrendingUpIcon className="size-6 text-muted-foreground" />
              </span>
              <div className="grid max-w-md gap-1.5">
                <p className="text-lg font-medium">No trends collected yet</p>
                <p className="text-sm text-muted-foreground">
                  {enabledCount
                    ? `ContentPulse checks ${enabledCount} source${enabledCount === 1 ? "" : "s"} on your schedule. Run discovery now to see what's rising.`
                    : "Enable at least one source to start discovering trends."}
                </p>
              </div>
              {canDiscover && enabledCount > 0 ? (
                <Button
                  onClick={() => discover.mutate({}, { onSuccess: onDiscoverStarted, onError: onDiscoverError })}
                  disabled={discover.isPending}
                >
                  <RadarIcon />
                  Discover trends now
                </Button>
              ) : (
                <Link href="/trends/sources" className={buttonVariants({ variant: "outline" })}>
                  Set up sources
                </Link>
              )}
            </CardContent>
          </Card>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-3">
              <Tabs value={filters.status} onValueChange={(v) => update({ status: v as TrendFilters["status"] })}>
                <TabsList>
                  <TabsTrigger value="active">Active</TabsTrigger>
                  <TabsTrigger value="shortlisted">Shortlisted</TabsTrigger>
                  <TabsTrigger value="rejected">Rejected</TabsTrigger>
                </TabsList>
              </Tabs>
              <Input
                aria-label="Search trends"
                placeholder="Search topics and keywords"
                value={filters.q}
                onChange={(e) => update({ q: e.target.value })}
                className="w-full sm:w-56"
              />
              <div className="flex flex-wrap gap-2 sm:ml-auto">
                <SimpleSelect
                  aria-label="Relevance"
                  value={filters.relevance || "all"}
                  onChange={(v) => update({ relevance: v === "all" ? "" : (v as RelevanceFilter) })}
                  options={RELEVANCE_FILTERS}
                  className="w-44"
                />
                <SimpleSelect
                  aria-label="Source"
                  value={filters.source || "all"}
                  onChange={(v) => update({ source: v === "all" ? "" : v })}
                  options={sourceOptions}
                  className="w-40"
                />
                <SimpleSelect
                  aria-label="Location"
                  value={filters.location || "all"}
                  onChange={(v) => update({ location: v === "all" ? "" : v })}
                  options={locationOptions}
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

            {trends.isPending ? (
              <div className="grid gap-3">
                {Array.from({ length: 5 }, (_, i) => (
                  <Skeleton key={i} className="h-20 w-full rounded-xl" />
                ))}
              </div>
            ) : trends.data?.items.length ? (
              <>
                <ul
                  className={cn("grid min-w-0 grid-cols-1 gap-3 transition-opacity", trends.isPlaceholderData && "opacity-50")}
                  aria-label="Trends"
                  aria-busy={trends.isPlaceholderData}
                >
                  {trends.data.items.map((trend) => (
                    <TrendRow key={trend.id} trend={trend} canReview={canReview} marketNames={marketNames} />
                  ))}
                </ul>
                {trends.data.total > trends.data.items.length && (
                  <Button variant="outline" className="justify-self-center" onClick={() => setLimit((n) => n + PAGE)}>
                    Show more ({trends.data.total - trends.data.items.length} left)
                  </Button>
                )}
              </>
            ) : (
              <p className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">
                {filters.q || filters.source || filters.location || filters.relevance
                  ? "No trends match these filters."
                  : filters.status === "active"
                    ? running
                      ? "Collecting… trends will appear here shortly."
                      : "No active trends right now."
                    : `No ${filters.status} trends.`}
                {filters.source && ` (${sourceName(filters.source)})`}
              </p>
            )}
          </>
        )}
      </div>
    </>
  );
}

const onDiscoverStarted = () => toast.success("Discovery started. Results appear here in a minute.");

function onDiscoverError(error: unknown) {
  if (error instanceof ApiError && error.status === 409) {
    toast.message("Discovery is already running. Results will appear here shortly.");
  } else {
    toast.error(errorMessage(error));
  }
}

/** Refresh trends and notify when a discovery run finishes. */
function useRunCompletion(runId: string | undefined, status: string | undefined) {
  const queryClient = useQueryClient();
  const orgId = useOrgId();
  const previous = useRef<{ id?: string; status?: string }>({});

  useEffect(() => {
    const before = previous.current;
    previous.current = { id: runId, status };
    const wasActive = before.status === "queued" || before.status === "running";
    if (!runId || before.id !== runId || !wasActive || status === before.status) return;
    if (status === "succeeded") {
      toast.success("New trends are in");
      queryClient.invalidateQueries({ queryKey: ["org", orgId, "trends"] });
      queryClient.invalidateQueries({ queryKey: ["org", orgId, "dashboard"] });
    } else if (status === "failed") {
      toast.error("Trend discovery failed. See the run details for each source.");
    }
  }, [runId, status, queryClient, orgId]);
}
