"use client";

import { useQueryClient } from "@tanstack/react-query";
import {
  ArrowDownIcon,
  ArrowRightIcon,
  ArrowUpIcon,
  CheckCircle2Icon,
  CheckIcon,
  FileTextIcon,
  ListChecksIcon,
  PaletteIcon,
  SearchIcon,
  SendIcon,
  SparklesIcon,
  TargetIcon,
  TrendingUpIcon,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/shared/page-header";
import { SimpleSelect } from "@/components/shared/simple-select";
import { PlatformTag, Tag } from "@/components/shared/tag";
import { sourceStatus } from "@/components/trends/sources-manager";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useKnowledgeSummary } from "@/hooks/use-knowledge";
import {
  useBrand,
  useDashboard,
  useDashboardOverview,
  useMembers,
  useOrganization,
  useOrgId,
  useOrgSettings,
  useServices,
} from "@/hooks/use-organization";
import { useTrendAction, useTrendSources } from "@/hooks/use-trends";
import { errorMessage } from "@/lib/api";
import { useCan, useMe } from "@/lib/auth";
import { POST_STATUS_LABEL } from "@/lib/content";
import { timeAgo } from "@/lib/format";
import { POST_STATUS_TONE, RELEVANCE_TONE } from "@/lib/tones";
import { PLATFORM_LABEL } from "@/lib/topics";
import { sourceName } from "@/lib/trends";
import { cn } from "@/lib/utils";
import { nextAction } from "@/lib/workflow";
import type {
  DashboardMetric,
  DashboardOverview,
  DashboardSummary,
  DashboardTrendingTopic,
  Platform,
  TopTrend,
} from "@/types/api";

const PERIODS = [
  { value: "7", label: "Last 7 days" },
  { value: "30", label: "Last 30 days" },
  { value: "90", label: "Last 90 days" },
] as const;

export function Dashboard() {
  const me = useMe();
  const can = useCan();
  const org = useOrganization();
  const summary = useDashboard();
  const [days, setDays] = useState(7);
  const overview = useDashboardOverview(days);
  const setup = useSetupSteps();
  const firstName = me.data?.name?.split(" ")[0];
  // Admins see setup first until the essentials are done (inviting a team is optional).
  const showSetup =
    can("organization.write") && !setup.loading && !setup.essentialsDone;
  const data = overview.data;

  return (
    <>
      <PageHeader
        title={firstName ? `Welcome back, ${firstName}` : "Dashboard"}
        description={
          org.data
            ? `What's happening with ${org.data.name}'s trends and content.`
            : "What's happening with your trends and content."
        }
        actions={
          <>
            {can("trends.read") && <TrendSearch />}
            <SimpleSelect
              aria-label="Period"
              value={String(days)}
              onChange={(v) => setDays(Number(v))}
              options={PERIODS}
              className="w-40"
            />
          </>
        }
      />

      <div className="grid gap-6">
        {showSetup && <SetupChecklist setup={setup} />}

        <section
          aria-label="Key numbers"
          className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4"
        >
          {data ? (
            <>
              <MetricCard
                label="Trends discovered"
                icon={TrendingUpIcon}
                metric={data.trends_discovered}
                days={days}
                href="/trends"
                color="var(--success)"
              />
              <MetricCard
                label="Relevant trends"
                icon={TargetIcon}
                metric={data.relevant_trends}
                days={days}
                href="/trends"
                color="var(--wire)"
              />
              <MetricCard
                label="Posts written"
                icon={FileTextIcon}
                metric={data.posts_generated}
                days={days}
                href="/content"
                color="var(--paper-8)"
              />
              <MetricCard
                label="Approved to publish"
                icon={SendIcon}
                metric={data.approved_posts}
                days={days}
                href="/approvals"
                color="var(--flash)"
              />
            </>
          ) : (
            Array.from({ length: 4 }, (_, i) => (
              <Skeleton key={i} className="h-32 w-full rounded-xl" />
            ))
          )}
        </section>

        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_20rem]">
          {/* Main column */}
          <div className="grid min-w-0 content-start gap-6">
            {can("trends.read") && <TrendingTopics data={data} />}

            <ContentPipeline summary={summary.data} overview={data} />

            <div className="grid gap-6 lg:grid-cols-2">
              <RecentContent data={data} />
              {can("trends.read") && (
                <TopOpportunities summary={summary.data} />
              )}
            </div>
          </div>

          {/* Side column */}
          <aside
            aria-label="At a glance"
            className="grid min-w-0 content-start gap-6"
          >
            {summary.data ? (
              <NextStepCallout summary={summary.data} />
            ) : (
              <Skeleton className="h-36 w-full rounded-xl" />
            )}
            {can("trends.read") && <SourceHealth />}
            <PlatformBreakdown data={data} />
          </aside>
        </div>
      </div>
    </>
  );
}

// --- Header search -------------------------------------------------------------------

function TrendSearch() {
  const router = useRouter();
  const [q, setQ] = useState("");
  return (
    <form
      role="search"
      className="relative"
      onSubmit={(e) => {
        e.preventDefault();
        const query = q.trim();
        // The Trends page keeps its filters in this tab's storage: hand it the query.
        try {
          const key = "cp:trends";
          const saved = JSON.parse(window.sessionStorage.getItem(key) ?? "{}");
          window.sessionStorage.setItem(
            key,
            JSON.stringify({ ...saved, q: query, status: "active" }),
          );
        } catch {
          // Storage unavailable: the Trends page opens unfiltered.
        }
        router.push("/trends");
      }}
    >
      <SearchIcon
        aria-hidden
        className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground"
      />
      <Input
        type="search"
        aria-label="Search trends"
        placeholder="Search trends…"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        className="w-56 pl-8"
      />
    </form>
  );
}

// --- Metric cards --------------------------------------------------------------------

function Change({ metric }: { metric: DashboardMetric }) {
  const { value, previous } = metric;
  if (previous === 0) {
    return value > 0 ? (
      <span className="text-xs font-medium text-success">New</span>
    ) : (
      <span className="text-xs text-muted-foreground">No change</span>
    );
  }
  const pct = Math.round(((value - previous) / previous) * 100);
  const up = pct >= 0;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-0.5 text-xs font-medium tabular-nums",
        up ? "text-success" : "text-destructive",
      )}
    >
      {up ? (
        <ArrowUpIcon className="size-3" aria-hidden />
      ) : (
        <ArrowDownIcon className="size-3" aria-hidden />
      )}
      {Math.abs(pct)}%
      <span className="sr-only">
        {up ? "up" : "down"} from {previous}
      </span>
    </span>
  );
}

/** A small line of the daily counts: the shape of the period, not decoration. */
function Sparkline({ series, color }: { series: number[]; color: string }) {
  const max = Math.max(...series, 1);
  const w = 100;
  const h = 32;
  const step = series.length > 1 ? w / (series.length - 1) : w;
  const points = series.map(
    (v, i) =>
      `${(i * step).toFixed(1)},${(h - 2 - (v / max) * (h - 4)).toFixed(1)}`,
  );
  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      preserveAspectRatio="none"
      aria-hidden
      className="h-10 w-full"
    >
      <polyline
        points={`0,${h} ${points.join(" ")} ${w},${h}`}
        fill={color}
        fillOpacity={0.1}
        stroke="none"
      />
      <polyline
        points={points.join(" ")}
        fill="none"
        stroke={color}
        strokeWidth={2}
        vectorEffect="non-scaling-stroke"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}

function MetricCard({
  label,
  icon: Icon,
  metric,
  days,
  href,
  color,
}: {
  label: string;
  icon: typeof TrendingUpIcon;
  metric: DashboardMetric;
  days: number;
  href: string;
  color: string;
}) {
  return (
    <Link
      href={href}
      className="group grid gap-3 rounded-xl border bg-card p-4 transition-colors outline-none hover:bg-muted/40 focus-visible:ring-3 focus-visible:ring-ring/50"
    >
      <span className="flex items-center gap-2.5">
        <span className="grid size-8 place-items-center rounded-lg bg-muted">
          <Icon className="size-4" aria-hidden />
        </span>
        <span className="text-sm font-medium">{label}</span>
      </span>
      <span className="grid gap-1">
        <span className="flex flex-wrap items-baseline gap-x-2">
          <span className="text-3xl leading-none font-semibold tabular-nums">
            {metric.value.toLocaleString()}
          </span>
          <Change metric={metric} />
        </span>
        <span className="text-xs text-muted-foreground">
          vs. previous {days} days
        </span>
      </span>
      <Sparkline series={metric.series} color={color} />
    </Link>
  );
}

// --- Trending topics -------------------------------------------------------------------

type RelevanceFilter = "all" | "high" | "medium" | "low";
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

function TrendingTopics({ data }: { data?: DashboardOverview }) {
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
              : "No trends collected in this period yet. Run discovery on the Trends page."}
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
                  <th scope="col" className="py-2 pr-3 font-medium">
                    Score
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
          href={`/trends/${t.id}`}
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
            {Math.round(t.opportunity_score)}
          </Tag>
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </td>
      <td className="py-2.5 pr-3 whitespace-nowrap tabular-nums">
        {t.momentum != null ? (
          <span className="inline-flex items-center gap-1">
            <ArrowUpIcon className="size-3 text-success" aria-hidden />
            {t.momentum}
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
        {t.shortlisted || !canShortlist ? (
          <Link
            href={`/trends/${t.id}`}
            className={buttonVariants({ variant: "outline", size: "sm" })}
          >
            {t.shortlisted ? "Shortlisted" : "Open"}
          </Link>
        ) : (
          <Button
            variant="outline"
            size="sm"
            disabled={action.isPending}
            aria-label={`Shortlist ${t.topic}`}
            onClick={() =>
              action.mutate(
                { id: t.id, action: "shortlist" },
                {
                  onSuccess: () => {
                    toast.success(
                      `Shortlisted “${t.topic}”. Plan a post from Topics.`,
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

function ContentPipeline({
  summary,
  overview,
}: {
  summary?: DashboardSummary;
  overview?: DashboardOverview;
}) {
  const stages = overview
    ? [
        {
          label: "Shortlisted",
          value: summary?.shortlisted_topics ?? 0,
          href: "/topics",
          icon: ListChecksIcon,
        },
        {
          label: "Drafts",
          value: overview.pipeline.draft,
          href: "/content",
          icon: FileTextIcon,
        },
        {
          label: "In design",
          value: overview.pipeline.design,
          href: "/design",
          icon: PaletteIcon,
        },
        {
          label: "Waiting approval",
          value: overview.pipeline.approval,
          href: "/approvals",
          icon: CheckCircle2Icon,
        },
        {
          label: "Ready to publish",
          value: overview.pipeline.ready,
          href: "/approvals",
          icon: SendIcon,
        },
      ]
    : [];
  return (
    <section
      aria-labelledby="pipeline-title"
      className="rounded-xl border bg-card p-4"
    >
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 id="pipeline-title" className="text-base font-semibold">
            Content pipeline
          </h2>
          <p className="text-xs text-muted-foreground">
            Where every post is right now, from topic to ready to publish.
          </p>
        </div>
        {overview && overview.pipeline.changes > 0 && (
          <Link
            href="/content"
            className="text-xs font-medium text-warning underline-offset-4 hover:underline"
          >
            {overview.pipeline.changes} sent back for changes
          </Link>
        )}
      </div>
      {!overview ? (
        <Skeleton className="h-16 w-full" />
      ) : (
        <ol className="grid grid-cols-2 gap-2 sm:grid-cols-5">
          {stages.map((stage, i) => (
            <li key={stage.label} className="relative">
              <Link
                href={stage.href}
                className="grid h-full justify-items-center gap-1 rounded-lg p-2 text-center transition-colors outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50"
              >
                <span className="grid size-9 place-items-center rounded-full bg-muted">
                  <stage.icon className="size-4" aria-hidden />
                </span>
                <span
                  className={cn(
                    "text-xl leading-tight font-semibold tabular-nums",
                    stage.value === 0 && "text-muted-foreground",
                  )}
                >
                  {stage.value}
                </span>
                <span className="text-xs text-muted-foreground">
                  {stage.label}
                </span>
              </Link>
              {i < stages.length - 1 && (
                <ArrowRightIcon
                  className="absolute top-6 -right-2 hidden size-4 text-muted-foreground sm:block"
                  aria-hidden
                />
              )}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

// --- Recent content & top opportunities ---------------------------------------------

function RecentContent({ data }: { data?: DashboardOverview }) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-2">
          <CardTitle>Recent content</CardTitle>
          <Link
            href="/content"
            className="text-xs font-medium whitespace-nowrap underline-offset-4 hover:underline"
          >
            View all
          </Link>
        </div>
      </CardHeader>
      <CardContent>
        {!data ? (
          <Skeleton className="h-40 w-full" />
        ) : data.recent_posts.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Posts you write appear here. Start from a shortlisted topic.
          </p>
        ) : (
          <ul className="divide-y" aria-label="Recent content">
            {data.recent_posts.map((p) => (
              <li key={p.id}>
                <Link
                  href={`/content/${p.id}`}
                  className="-mx-2 grid gap-1.5 rounded-md px-2 py-2.5 hover:bg-muted/60"
                >
                  <span className="truncate text-sm font-medium">
                    {p.title?.trim() || "Untitled post"}
                  </span>
                  <span className="flex flex-wrap items-center gap-2">
                    <PlatformTag platform={p.platform} />
                    <Tag tone={POST_STATUS_TONE[p.status]} dot>
                      {POST_STATUS_LABEL[p.status]}
                    </Tag>
                    <time
                      dateTime={p.updated_at}
                      className="ml-auto text-xs text-muted-foreground"
                    >
                      {timeAgo(p.updated_at)}
                    </time>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function TopOpportunities({ summary }: { summary?: DashboardSummary }) {
  const trends: TopTrend[] = summary?.top_trends.slice(0, 5) ?? [];
  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-2">
          <div className="grid gap-1">
            <CardTitle>Top opportunities</CardTitle>
            <CardDescription>
              Best-scoring trends from the last week.
            </CardDescription>
          </div>
          <Link
            href="/trends"
            className="text-xs font-medium whitespace-nowrap underline-offset-4 hover:underline"
          >
            View all
          </Link>
        </div>
      </CardHeader>
      <CardContent>
        {!summary ? (
          <Skeleton className="h-40 w-full" />
        ) : trends.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            The best-scoring trends appear here once trends have been collected.
          </p>
        ) : (
          <ol className="divide-y">
            {trends.map((t) => (
              <li key={t.id}>
                <Link
                  href={`/trends/${t.id}`}
                  className="-mx-2 flex items-center gap-3 rounded-md px-2 py-2.5 hover:bg-muted/60"
                >
                  <span className="grid min-w-0 flex-1">
                    <span className="truncate text-sm font-medium">
                      {t.topic}
                    </span>
                    <span className="truncate text-xs text-muted-foreground">
                      {t.sources.map(sourceName).join(" · ")}
                    </span>
                  </span>
                  <span className="grid size-9 shrink-0 place-items-center rounded-full bg-success/15 text-sm font-semibold tabular-nums">
                    {t.opportunity_score != null
                      ? Math.round(t.opportunity_score)
                      : "—"}
                  </span>
                </Link>
              </li>
            ))}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}

// --- Side column -----------------------------------------------------------------------

function NextStepCallout({ summary }: { summary: DashboardSummary }) {
  const can = useCan();
  const next = nextAction(summary, can);
  return (
    <section
      aria-labelledby="next-step-title"
      className="dark grid gap-3 rounded-xl bg-background p-5 text-foreground"
    >
      <SparklesIcon className="size-5 text-flash" aria-hidden />
      <div className="grid gap-1">
        <h2 id="next-step-title" className="text-base font-semibold">
          {next.title}
        </h2>
        <p className="text-sm text-muted-foreground">{next.detail}</p>
      </div>
      <Link
        href={next.href}
        className={cn(
          buttonVariants({ variant: "secondary" }),
          "justify-self-start",
        )}
      >
        {next.cta} <ArrowRightIcon />
      </Link>
    </section>
  );
}

const PLATFORM_COLOR: Record<Platform, string> = {
  linkedin: "#0a66c2",
  x: "#52525b",
  instagram: "#e1306c",
  facebook: "#4f46e5",
  blog: "#0d9488",
};

function PlatformBreakdown({ data }: { data?: DashboardOverview }) {
  const entries = (
    Object.entries(data?.platform_breakdown ?? {}) as [Platform, number][]
  )
    .filter(([, n]) => n > 0)
    .sort((a, b) => b[1] - a[1]);
  const total = entries.reduce((sum, [, n]) => sum + n, 0);
  // Donut from stroke-dasharray arcs on a circle of circumference 100: each
  // arc starts where the previous ones end.
  const arcs = entries.map(([platform, n], i) => ({
    platform,
    share: (n / total) * 100,
    start: entries
      .slice(0, i)
      .reduce((sum, [, m]) => sum + (m / total) * 100, 0),
  }));
  return (
    <Card>
      <CardHeader>
        <CardTitle>Platform breakdown</CardTitle>
        <CardDescription>Posts by platform, all time.</CardDescription>
      </CardHeader>
      <CardContent>
        {!data ? (
          <Skeleton className="h-36 w-full" />
        ) : total === 0 ? (
          <p className="text-sm text-muted-foreground">No posts yet.</p>
        ) : (
          <div className="flex items-center gap-5">
            <div
              className="relative size-32 shrink-0"
              role="img"
              aria-label={`${total} posts: ${entries.map(([p, n]) => `${PLATFORM_LABEL[p]} ${n}`).join(", ")}`}
            >
              <svg viewBox="0 0 42 42" className="size-full -rotate-90">
                <circle
                  cx="21"
                  cy="21"
                  r="15.915"
                  fill="none"
                  stroke="var(--muted)"
                  strokeWidth="6"
                />
                {arcs.map(({ platform, share, start }) => (
                  <circle
                    key={platform}
                    cx="21"
                    cy="21"
                    r="15.915"
                    fill="none"
                    stroke={PLATFORM_COLOR[platform]}
                    strokeWidth="6"
                    strokeDasharray={`${share} ${100 - share}`}
                    strokeDashoffset={-start}
                  />
                ))}
              </svg>
              <span className="absolute inset-0 grid place-content-center text-center">
                <span className="text-2xl leading-none font-semibold tabular-nums">
                  {total}
                </span>
                <span className="text-[11px] text-muted-foreground">posts</span>
              </span>
            </div>
            <ul className="grid flex-1 gap-1.5 text-sm">
              {entries.map(([platform, n]) => (
                <li key={platform} className="flex items-center gap-2">
                  <span
                    aria-hidden
                    className="size-2.5 shrink-0 rounded-full"
                    style={{ background: PLATFORM_COLOR[platform] }}
                  />
                  <span className="flex-1">{PLATFORM_LABEL[platform]}</span>
                  <span className="text-muted-foreground tabular-nums">
                    {n} ({Math.round((n / total) * 100)}%)
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function SourceHealth() {
  const sources = useTrendSources();
  const enabled = (sources.data ?? []).filter(
    (s) => s.enabled && s.pricing !== "unavailable",
  );
  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-2">
          <CardTitle>Source health</CardTitle>
          <Link
            href="/trends/sources"
            className="text-xs font-medium whitespace-nowrap underline-offset-4 hover:underline"
          >
            View all
          </Link>
        </div>
      </CardHeader>
      <CardContent>
        {!sources.data ? (
          <Skeleton className="h-32 w-full" />
        ) : enabled.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No sources are on yet.
          </p>
        ) : (
          <ul className="grid gap-2.5" aria-label="Source health">
            {enabled.slice(0, 7).map((s) => {
              const status = sourceStatus(s);
              return (
                <li key={s.key} className="flex items-center gap-2 text-sm">
                  <span className="min-w-0 flex-1 truncate">{s.name}</span>
                  <span className="flex items-center gap-1.5 text-xs">
                    <span
                      className={cn("size-1.5 rounded-full", status.tone)}
                      aria-hidden
                    />
                    {status.label}
                  </span>
                  <span className="w-16 text-right text-xs text-muted-foreground">
                    {s.last_success_at ? timeAgo(s.last_success_at) : "—"}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

// --- Setup checklist (admins, until the essentials are done) -------------------------

interface SetupStep {
  done: boolean;
  optional?: boolean;
  title: string;
  detail: string;
  href: string;
}

function useSetupSteps() {
  const org = useOrganization();
  const settings = useOrgSettings();
  const brand = useBrand();
  const services = useServices();
  const members = useMembers();
  const canReadKnowledge = useCan()("knowledge.read");
  const knowledge = useKnowledgeSummary({ enabled: canReadKnowledge });

  const loading = [org, settings, brand, services, members].some(
    (q) => q.isPending,
  );
  const steps: SetupStep[] = [
    {
      done: !!org.data?.description,
      title: "Describe your organization",
      detail: "A sentence or two about what you do.",
      href: "/organization/profile",
    },
    {
      done: (services.data?.length ?? 0) > 0,
      title: "List your services and products",
      detail: "Trends are matched against these, so be specific.",
      href: "/organization/services",
    },
    {
      done: !!brand.data?.brand_voice,
      title: "Describe your brand voice",
      detail: "How you sound, and words to avoid.",
      href: "/organization/brand",
    },
    {
      done: !!settings.data?.target_markets.length,
      title: "Choose your markets and audience",
      detail: "Where your audience is and who you're writing for.",
      href: "/organization/content-setup#audience",
    },
    {
      done: !!settings.data?.enabled_platforms.length,
      title: "Turn on your platforms",
      detail: "Where you post. Content is only written for these.",
      href: "/organization/content-setup#platforms",
    },
    ...(canReadKnowledge
      ? [
          {
            done: (knowledge.data?.indexed_documents ?? 0) > 0,
            title: "Add your website to the knowledge base",
            detail: "So posts only say things your website backs up.",
            href: "/organization/knowledge",
          },
        ]
      : []),
    {
      done: (members.data?.length ?? 0) > 1,
      title: "Invite your team",
      detail:
        "Creators who write and design posts, and viewers. Optional if you work alone.",
      href: "/team",
      optional: true,
    },
  ];
  return {
    steps,
    completed: steps.filter((s) => s.done).length,
    essentialsDone: steps.every((s) => s.done || s.optional),
    loading,
  };
}

function SetupChecklist({
  setup,
}: {
  setup: ReturnType<typeof useSetupSteps>;
}) {
  const { steps, completed } = setup;
  const first =
    steps.find((s) => !s.done && !s.optional) ?? steps.find((s) => !s.done);
  return (
    <Card>
      <CardHeader className="gap-3">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="grid gap-1">
            <CardTitle className="text-lg">Set up your workspace</CardTitle>
            <CardDescription>
              About 10 minutes. ContentPulse uses this to decide which trends
              matter to you and to write posts in your voice.
            </CardDescription>
          </div>
          {first && (
            <Link href={first.href} className={buttonVariants()}>
              {completed === 0 ? "Start setup" : "Continue setup"}
              <ArrowRightIcon />
            </Link>
          )}
        </div>
        <div className="flex items-center gap-3">
          <div
            className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted"
            role="progressbar"
            aria-label="Setup progress"
            aria-valuemin={0}
            aria-valuemax={steps.length}
            aria-valuenow={completed}
          >
            <div
              className="h-full rounded-full bg-primary transition-[width] duration-500"
              style={{ width: `${(completed / steps.length) * 100}%` }}
            />
          </div>
          <span className="text-xs text-muted-foreground tabular-nums">
            {completed} of {steps.length} done.
          </span>
        </div>
      </CardHeader>
      <CardContent>
        <ul className="grid gap-0.5 sm:grid-cols-2 sm:gap-x-6">
          {steps.map((step) => (
            <li key={step.href}>
              <Link
                href={step.href}
                className="group -mx-2 flex items-center gap-3 rounded-lg p-2 transition-colors hover:bg-muted"
              >
                <span
                  className={cn(
                    "grid size-5 shrink-0 place-items-center rounded-full border",
                    step.done &&
                      "border-primary bg-primary text-primary-foreground",
                  )}
                >
                  {step.done && <CheckIcon className="size-3" />}
                  <span className="sr-only">
                    {step.done ? "Done:" : "To do:"}
                  </span>
                </span>
                <span className="grid min-w-0 flex-1 gap-0.5">
                  <span
                    className={cn(
                      "text-sm font-medium",
                      step.done &&
                        "text-muted-foreground line-through decoration-muted-foreground/40",
                    )}
                  >
                    {step.title}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {step.detail}
                  </span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
