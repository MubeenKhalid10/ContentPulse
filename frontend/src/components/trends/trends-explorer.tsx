"use client";

import { RadarIcon, SlidersHorizontalIcon, TrendingUpIcon, XIcon } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { FILTER_SEARCH, FILTER_SELECT, FilterBar } from "@/components/shared/filter-bar";
import { PageHeader } from "@/components/shared/page-header";
import { SearchInput } from "@/components/shared/search-input";
import { SimpleSelect } from "@/components/shared/simple-select";
import { BackgroundDiscoveryToggle } from "@/components/trends/background-discovery";
import { TrendRow } from "@/components/trends/trend-row";
import { TrendsExport } from "@/components/trends/trends-export";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { usePersistedState } from "@/hooks/use-persisted-state";
import { useOrgSettings } from "@/hooks/use-organization";
import {
  TREND_WINDOW_DAYS,
  type RelevanceFilter,
  type TrendFilters,
  useAIStatus,
  useDiscover,
  useDiscoveryRuns,
  useMarkets,
  useTrendSources,
  useTrends,
} from "@/hooks/use-trends";
import { errorMessage } from "@/lib/api";
import { useCan } from "@/lib/auth";
import { sourceName } from "@/lib/trends";
import { cn } from "@/lib/utils";

import { onDiscoverStarted, onDiscoverError, useRunCompletion } from "./use-run-completion";
import { DiscoveryStatus } from "./discovery-status";
import { FilterField } from "./filter-field";
import { SourcesStrip } from "./sources-strip";

const PAGE = 30;

const RELEVANCE_FILTERS = [
  { value: "relevant", label: "Relevant to us" },
  { value: "all", label: "Any relevance" },
  { value: "highly_relevant", label: "Highly relevant" },
  { value: "weakly_relevant", label: "Weakly relevant" },
  { value: "not_relevant", label: "Not relevant" },
  { value: "unanalyzed", label: "Not analyzed yet" },
];

const SORTS = [
  { value: "score", label: "Best opportunity" },
  { value: "recent", label: "Latest activity" },
  { value: "mentions", label: "Most mentioned" },
  { value: "new", label: "First seen" },
] as const;

export function TrendsExplorer() {
  const can = useCan();
  const canDiscover = can("trends.manage");
  const canReview = can("trends.manage") || can("topics.manage");
  const [saved, setFilters] = usePersistedState<TrendFilters>("trends-v2", {
    status: "active",
    // Any relevance by default; the filter applies only when the user sets it.
    relevance: "",
    sort: "score",
    source: "",
    location: "",
    q: "",
  });
  // The Rejected tab is gone: rejected trends are in All trends, with Restore.
  const filters: TrendFilters =
    saved.status === ("rejected" as string) ? { ...saved, status: "all" } : saved;
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

  const marketNames = useMemo(
    () => new Map(markets.data?.map((m) => [m.code, m.name])),
    [markets.data],
  );
  const sourceOptions = [
    { value: "all", label: "All sources" },
    ...(sources.data ?? [])
      .filter((s) => s.enabled)
      .map((s) => ({ value: s.key, label: s.name })),
  ];
  const locationCodes = Array.from(
    new Set(trends.data?.items.flatMap((t) => t.locations) ?? []),
  );
  const locationOptions = [
    { value: "all", label: "All locations" },
    ...locationCodes.map((c) => ({
      value: c,
      label: marketNames.get(c) ?? (c === "GLOBAL" ? "Global" : c),
    })),
  ];

  const [showFilters, setShowFilters] = useState(false);
  // Only what differs from the default view counts as an active filter.
  const activeFilters = [
    ...(filters.relevance
      ? [
          {
            key: "relevance",
            label: RELEVANCE_FILTERS.find((o) => o.value === (filters.relevance || "all"))?.label ?? "Relevance",
            clear: () => update({ relevance: "" }),
          },
        ]
      : []),
    ...(filters.source
      ? [{ key: "source", label: sourceName(filters.source), clear: () => update({ source: "" }) }]
      : []),
    ...(filters.location
      ? [
          {
            key: "location",
            label: marketNames.get(filters.location) ?? (filters.location === "GLOBAL" ? "Global" : filters.location),
            clear: () => update({ location: "" }),
          },
        ]
      : []),
  ];

  const update = (patch: Partial<TrendFilters>) => {
    setFilters((f) => ({ ...f, ...patch }));
    setLimit(PAGE);
  };

  const runDiscovery = () => {
    const shownAt = trends.dataUpdatedAt;
    discover.mutate(
      {},
      {
        onSuccess: (result) => onDiscoverStarted(result, shownAt),
        onError: onDiscoverError,
      },
    );
  };

  const noRunsYet = runs.data && runs.data.length === 0;
  const enabledCount = settings.data?.enabled_sources.length ?? 0;
  const showAnyRelevance = () => update({ relevance: "" });

  return (
    <>
      <PageHeader
        title="Find trends"
        contentClassName="max-w-[430px]"
        actionsClassName="ml-auto justify-end gap-3"
        description={
          <>
            Everything that
            is rising in your markets right now, scored for how well it fits
            your business. Shortlist the trends worth posting about.{" "}
            {ai.data && (
              <span className="sm:whitespace-nowrap">
                {ai.data.engine === "ai"
                  ? "Relevance is checked by AI."
                  : "Relevance is a basic keyword match. AI analysis isn't switched on for this workspace."}
              </span>
            )}
          </>
        }
        actions={
          canDiscover && (
            <Button
              disabled={running || discover.isPending || enabledCount === 0}
              title={
                enabledCount === 0
                  ? "Turn on at least one source in Discovery Sources first."
                  : running
                    ? "A check is already running."
                    : undefined
              }
              onClick={runDiscovery}
            >
              <RadarIcon />
              {running ? "Checking…" : "Check for new trends"}
            </Button>
          )
        }
      />

      <div className="grid min-w-0 grid-cols-1 gap-6">
        {canDiscover && (enabledCount === 0 || running) && (
          <p className="text-sm text-muted-foreground" role="status">
            {enabledCount === 0 ? (
              <>
                &ldquo;Check for new trends&rdquo; is off because no sources are
                turned on.{" "}
                <Link href="/trends/sources" className="font-medium text-foreground underline underline-offset-2">
                  Turn on a source in Discovery Sources
                </Link>
                .
              </>
            ) : (
              "A check is already running. The button is back when it finishes."
            )}
          </p>
        )}
        <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2">
          <DiscoveryStatus />
          <BackgroundDiscoveryToggle className="ml-auto" />
        </div>
        {can("trends.export") && <TrendsExport />}
        {sources.data && <SourcesStrip sources={sources.data} />}

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
                    ? `ContentPulse checks ${enabledCount} source${enabledCount === 1 ? "" : "s"}${settings.data?.background_discovery ? " in the background" : " when you ask"}. Run discovery now to see what's rising.`
                    : "Enable at least one source to start discovering trends."}
                </p>
              </div>
              {canDiscover && enabledCount > 0 ? (
                <Button
                  onClick={runDiscovery}
                  disabled={discover.isPending}
                >
                  <RadarIcon />
                  Check for new trends
                </Button>
              ) : (
                <Link
                  href="/trends/sources"
                  className={buttonVariants({ variant: "outline" })}
                >
                  Set up sources
                </Link>
              )}
            </CardContent>
          </Card>
        ) : (
          <>
            <div className="grid gap-3">
              <FilterBar>
                <Tabs
                  value={filters.status}
                  onValueChange={(v) =>
                    update({ status: v as TrendFilters["status"] })
                  }
                  className="shrink-0"
                >
                  <TabsList>
                    <TabsTrigger value="all">All trends</TabsTrigger>
                    <TabsTrigger value="active">To review</TabsTrigger>
                    <TabsTrigger value="shortlisted">Shortlisted</TabsTrigger>
                  </TabsList>
                </Tabs>
                <SearchInput
                  aria-label="Search trends"
                  placeholder="Search trends"
                  value={filters.q}
                  onChange={(q) => update({ q })}
                  className={FILTER_SEARCH}
                />
                <SimpleSelect
                  aria-label="Sort by"
                  value={filters.sort}
                  onChange={(v) => update({ sort: v })}
                  options={SORTS}
                  className={FILTER_SELECT}
                />
                <Button
                  variant="outline"
                  aria-expanded={showFilters}
                  aria-controls="trend-filters"
                  aria-label={
                    activeFilters.length > 0
                      ? `Filters, ${activeFilters.length} active`
                      : "Filters"
                  }
                  onClick={() => setShowFilters((v) => !v)}
                >
                  <SlidersHorizontalIcon />
                  Filters
                  {activeFilters.length > 0 && (
                    <span className="ml-0.5 rounded-full bg-primary px-1.5 text-xs font-semibold text-primary-foreground">
                      {activeFilters.length}
                    </span>
                  )}
                </Button>
              </FilterBar>
              {showFilters && (
                <div
                  id="trend-filters"
                  className="grid gap-3 rounded-lg border bg-card p-3 sm:grid-cols-3"
                >
                  <FilterField id="trend-relevance" label="How well it fits you">
                    <SimpleSelect
                      id="trend-relevance"
                      value={filters.relevance || "all"}
                      onChange={(v) =>
                        update({
                          relevance: v === "all" ? "" : (v as RelevanceFilter),
                        })
                      }
                      options={RELEVANCE_FILTERS}
                    />
                  </FilterField>
                  <FilterField id="trend-source" label="Source">
                    <SimpleSelect
                      id="trend-source"
                      value={filters.source || "all"}
                      onChange={(v) => update({ source: v === "all" ? "" : v })}
                      options={sourceOptions}
                    />
                  </FilterField>
                  <FilterField id="trend-location" label="Location">
                    <SimpleSelect
                      id="trend-location"
                      value={filters.location || "all"}
                      onChange={(v) => update({ location: v === "all" ? "" : v })}
                      options={locationOptions}
                    />
                  </FilterField>
                </div>
              )}
              {activeFilters.length > 0 && (
                <ul className="flex flex-wrap items-center gap-1.5" aria-label="Active filters">
                  {activeFilters.map((f) => (
                    <li key={f.key}>
                      <button
                        type="button"
                        onClick={f.clear}
                        aria-label={`Remove filter: ${f.label}`}
                        className="inline-flex h-6 items-center gap-1 rounded-full bg-muted px-2.5 text-xs font-medium hover:bg-muted/70"
                      >
                        {f.label}
                        <XIcon className="size-3" aria-hidden />
                      </button>
                    </li>
                  ))}
                  {activeFilters.length > 0 && (
                  <li>
                    <Button
                      variant="ghost"
                      size="xs"
                      onClick={() =>
                        update({ relevance: "", source: "", location: "" })
                      }
                    >
                      Reset filters
                    </Button>
                  </li>
                  )}
                </ul>
              )}
            </div>

            {trends.isError ? (
              <div
                role="alert"
                className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-destructive/40 p-4 text-sm"
              >
                <span className="text-destructive">
                  Couldn&apos;t load trends. {errorMessage(trends.error)}
                </span>
                <Button variant="outline" size="sm" onClick={() => trends.refetch()}>
                  Retry
                </Button>
              </div>
            ) : trends.isPending ? (
              <div className="grid gap-3">
                {Array.from({ length: 5 }, (_, i) => (
                  <Skeleton key={i} className="h-20 w-full rounded-xl" />
                ))}
              </div>
            ) : trends.data?.items.length ? (
              <>
                <p className="text-sm text-muted-foreground">
                  {trends.data.total} trend{trends.data.total === 1 ? "" : "s"} from the last{" "}
                  {TREND_WINDOW_DAYS} days
                  {filters.relevance === "relevant" && ", the ones that fit your business"}.
                </p>
                <ul
                  className={cn(
                    "grid min-w-0 grid-cols-1 gap-3 transition-opacity",
                    trends.isPlaceholderData && "opacity-50",
                  )}
                  aria-label="Trends"
                  aria-busy={trends.isPlaceholderData}
                >
                  {trends.data.items.map((trend) => (
                    <TrendRow
                      key={trend.id}
                      trend={trend}
                      canReview={canReview}
                      marketNames={marketNames}
                    />
                  ))}
                </ul>
                {trends.data.total > trends.data.items.length && (
                  <Button
                    variant="outline"
                    className="justify-self-center"
                    onClick={() => setLimit((n) => n + PAGE)}
                  >
                    Show more ({trends.data.total - trends.data.items.length}{" "}
                    left)
                  </Button>
                )}
              </>
            ) : (
              <div className="grid justify-items-center gap-3 rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">
                <p>
                  {filters.q ||
                  filters.source ||
                  filters.location ||
                  (filters.relevance && filters.relevance !== "relevant")
                    ? `No trends match these filters${filters.source ? ` (${sourceName(filters.source)})` : ""}.`
                    : filters.relevance === "relevant"
                      ? "No trends match the “Relevant to us” filter."
                      : filters.status === "shortlisted"
                        ? "Nothing shortlisted yet. Shortlist a trend to plan posts for it."
                        : running
                          ? "Collecting… trends will appear here shortly."
                          : `No trends in the last ${TREND_WINDOW_DAYS} days.`}
                </p>
                {filters.relevance === "relevant" &&
                  !(filters.q || filters.source || filters.location) && (
                    <Button variant="outline" size="sm" onClick={showAnyRelevance}>
                      Show any relevance
                    </Button>
                  )}
              </div>
            )}
          </>
        )}
      </div>
    </>
  );
}
