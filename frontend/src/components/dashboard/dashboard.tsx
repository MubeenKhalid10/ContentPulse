"use client";

import { FileTextIcon, SendIcon, TargetIcon, TrendingUpIcon } from "lucide-react";
import { useState } from "react";

import { PageHeader } from "@/components/shared/page-header";
import { SimpleSelect } from "@/components/shared/simple-select";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useDashboard, useDashboardOverview, useOrganization } from "@/hooks/use-organization";
import { useCan, useMe } from "@/lib/auth";

import { HowItWorks } from "./how-it-works";
import { TrendSearch } from "./trend-search";
import { MetricCard } from "./metric-card";
import { TrendingTopics } from "./trending-topics";
import { RecentContent, NextStepCallout } from "./recent-content";
import { PlatformBreakdown } from "./platform-breakdown";
import { SourceHealth } from "./source-health";
import { useSetupSteps, SetupChecklist } from "./setup-checklist";

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
  const sm = summary.data;
  // Nothing has happened yet: show the guide, not a wall of empty charts.
  const isNew =
    !!sm &&
    sm.relevant_trends +
      sm.trends_today +
      sm.topics_to_review +
      sm.shortlisted_topics +
      sm.drafts +
      sm.design_pending +
      sm.pending_approval +
      sm.approved ===
      0;
  const [showAll, setShowAll] = useState(false);
  const simple = isNew && !showAll;

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
        {summary.data ? (
          <NextStepCallout summary={summary.data} />
        ) : (
          <Skeleton className="h-28 w-full rounded-xl" />
        )}

        {showSetup && <SetupChecklist setup={setup} />}

        {isNew && <HowItWorks />}

        {simple && (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-dashed p-4 text-sm text-muted-foreground">
            <span>
              Charts and trend lists appear here once ContentPulse has found
              your first trends.
            </span>
            <Button variant="outline" size="sm" onClick={() => setShowAll(true)}>
              Show the full dashboard anyway
            </Button>
          </div>
        )}

        {!simple && (
          <p className="-mb-3 text-xs text-muted-foreground">
            Showing the last {days} days. Platform breakdown and source health
            are not affected by the period.
          </p>
        )}

        {!simple && (
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
                  label="Ready to publish"
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
        )}

        {!simple && (
          <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_20rem]">
            {/* Main column */}
            <div className="grid min-w-0 content-start gap-6">
              {can("trends.read") && <TrendingTopics data={data} />}

              <RecentContent data={data} />
            </div>

            {/* Side column */}
            <aside
              aria-label="At a glance"
              className="grid min-w-0 content-start gap-6"
            >
              {can("trends.manage") && <SourceHealth />}
              <PlatformBreakdown data={data} />
            </aside>
          </div>
        )}
      </div>
    </>
  );
}

// --- How it works --------------------------------------------------------------------

export type RelevanceFilter = "all" | "high" | "medium" | "low";

export interface SetupStep {
  done: boolean;
  optional?: boolean;
  title: string;
  detail: string;
  href: string;
}
