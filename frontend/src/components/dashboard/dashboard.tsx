"use client";

import { ArrowRightIcon, CheckIcon, ChevronRightIcon } from "lucide-react";
import Link from "next/link";

import { PageHeader } from "@/components/shared/page-header";
import { Score } from "@/components/trends/score";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useKnowledgeSummary } from "@/hooks/use-knowledge";
import {
  useBrand,
  useDashboard,
  useMembers,
  useOrganization,
  useOrgSettings,
  useServices,
} from "@/hooks/use-organization";
import { useCan, useMe } from "@/lib/auth";
import { describeAction, timeAgo } from "@/lib/format";
import { sourceName } from "@/lib/trends";
import { cn } from "@/lib/utils";
import { WORKFLOW, nextAction, stepCounts } from "@/lib/workflow";
import type { DashboardSummary, TopTrend } from "@/types/api";

export function Dashboard() {
  const me = useMe();
  const summary = useDashboard();
  const org = useOrganization();
  const can = useCan();
  const setup = useSetupSteps();
  const firstName = me.data?.name?.split(" ")[0];
  // Admins see setup first until the essentials are done (inviting a team is
  // optional); everyone else starts with their next step.
  const showSetup = can("organization.write") && !setup.loading && !setup.essentialsDone;

  return (
    <>
      <PageHeader
        title={firstName ? `Welcome, ${firstName}` : "Dashboard"}
        description={org.data ? `What needs attention at ${org.data.name}.` : undefined}
      />

      <div className="grid gap-6">
        {setup.loading || !summary.data ? (
          <Skeleton className="h-40 w-full rounded-xl" />
        ) : showSetup ? (
          <SetupChecklist setup={setup} />
        ) : (
          <NextStep summary={summary.data} />
        )}

        <WorkflowOverview summary={summary.data} />

        {can("trends.read") ? (
          <div className="grid gap-6 lg:grid-cols-5">
            <div className="grid content-start gap-6 lg:col-span-3">
              {summary.data && summary.data.top_trends.length > 0 ? (
                <TopTrends trends={summary.data.top_trends} />
              ) : (
                summary.data && (
                  <Card>
                    <CardHeader>
                      <CardTitle>Top opportunities</CardTitle>
                      <CardDescription>
                        The best-scoring trends appear here once trends have been collected.
                      </CardDescription>
                    </CardHeader>
                    <CardContent>
                      <Link href="/trends" className={buttonVariants({ variant: "outline", size: "sm" })}>
                        Go to trends
                      </Link>
                    </CardContent>
                  </Card>
                )
              )}
            </div>
            <RecentActivity summary={summary.data} loading={summary.isPending} className="lg:col-span-2" />
          </div>
        ) : (
          // No Trends access: activity takes the full width.
          <RecentActivity summary={summary.data} loading={summary.isPending} />
        )}
      </div>
    </>
  );
}

function NextStep({ summary }: { summary: DashboardSummary }) {
  const can = useCan();
  const next = nextAction(summary, can);
  return (
    <section
      aria-labelledby="next-step-title"
      className="flex flex-wrap items-center gap-x-6 gap-y-4 rounded-xl border bg-card p-5 sm:p-6"
    >
      <div className="grid min-w-0 flex-1 basis-72 gap-1">
        <h2 id="next-step-title" className="text-lg font-semibold tracking-tight">
          {next.title}
        </h2>
        <p className="text-sm text-muted-foreground">{next.detail}</p>
      </div>
      <Link href={next.href} className={buttonVariants({ size: "lg" })}>
        {next.cta}
        <ArrowRightIcon />
      </Link>
    </section>
  );
}

/** The five steps, in order, with how much is sitting in each. */
function WorkflowOverview({ summary }: { summary?: DashboardSummary }) {
  const me = useMe();
  const steps = WORKFLOW.filter((s) => me.data?.permissions.includes(s.permission));
  const counts = summary ? stepCounts(summary) : null;
  return (
    <section aria-labelledby="workflow-title" className="grid gap-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="workflow-title" className="text-base font-semibold">
          How content moves
        </h2>
        <p className="text-xs text-muted-foreground">Every post moves through these steps in order.</p>
      </div>
      <ol
        className="grid gap-px overflow-hidden rounded-xl border bg-border sm:grid-cols-2 lg:[grid-template-columns:repeat(var(--steps),minmax(0,1fr))]"
        // However many steps this role can see, they share the full width.
        style={{ "--steps": steps.length } as React.CSSProperties}
      >
        {steps.map((step) => (
          <li
            key={step.href}
            className="bg-card sm:[&:last-child:nth-child(odd)]:col-span-2 lg:[&:last-child:nth-child(odd)]:col-span-1"
          >
            <Link
              href={step.href}
              title={step.summary}
              className="group grid h-full content-start gap-3 p-4 transition-colors hover:bg-muted/60 focus-visible:bg-muted/60 focus-visible:outline-none"
            >
              <span className="flex items-center gap-2">
                <span
                  aria-hidden
                  className="grid size-5 shrink-0 place-items-center rounded-full bg-primary text-[11px] font-semibold tabular-nums text-primary-foreground"
                >
                  {step.n}
                </span>
                <span className="text-sm font-medium">{step.label}</span>
                <ChevronRightIcon
                  aria-hidden
                  className="ml-auto size-4 text-muted-foreground transition-transform group-hover:translate-x-0.5"
                />
              </span>
              <span className="sr-only">{step.summary}</span>
              <span className="mt-1 flex flex-wrap gap-x-6 gap-y-2">
                {counts ? (
                  counts[step.href].map((c) => (
                    <span key={c.label} className="grid gap-1">
                      <span
                        className={cn(
                          "text-2xl leading-none font-semibold tabular-nums",
                          c.value === 0 && "text-muted-foreground/70",
                        )}
                      >
                        {c.value.toLocaleString()}
                      </span>
                      <span className="text-xs text-muted-foreground first-letter:uppercase">{c.label}</span>
                    </span>
                  ))
                ) : (
                  <Skeleton className="h-10 w-24" />
                )}
              </span>
            </Link>
          </li>
        ))}
      </ol>
    </section>
  );
}

function RecentActivity({
  summary,
  loading,
  className,
}: {
  summary?: DashboardSummary;
  loading: boolean;
  className?: string;
}) {
  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle>Recent activity</CardTitle>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="grid gap-3">
            {Array.from({ length: 4 }, (_, i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : summary?.recent_activity.length ? (
          <ul className="grid gap-3.5">
            {summary.recent_activity.map((item) => (
              <li key={item.id} className="grid gap-0.5 text-sm">
                <span>
                  <span className="font-medium">{item.user_name ?? "System"}</span>{" "}
                  <span className="text-muted-foreground">{describeAction(item.action)}</span>
                </span>
                <time dateTime={item.created_at} className="text-xs text-muted-foreground">
                  {timeAgo(item.created_at)}
                </time>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">
            Changes your team makes (new posts, approvals, settings) show up here.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

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

  const loading = [org, settings, brand, services, members].some((q) => q.isPending);
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
      done: !!(settings.data?.target_markets.length && settings.data?.enabled_platforms.length),
      title: "Choose markets and platforms",
      detail: "Where your audience is and where you post.",
      href: "/settings",
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
      detail: "Creators who write and design posts, and viewers. Optional if you work alone.",
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

function SetupChecklist({ setup }: { setup: ReturnType<typeof useSetupSteps> }) {
  const { steps, completed } = setup;
  const first = steps.find((s) => !s.done && !s.optional) ?? steps.find((s) => !s.done);
  return (
    <Card>
      <CardHeader className="gap-3">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="grid gap-1">
            <CardTitle className="text-lg">Set up your workspace</CardTitle>
            <CardDescription>
              About 10 minutes. ContentPulse uses this to decide which trends matter to you and to
              write posts in your voice.
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
                    step.done && "border-primary bg-primary text-primary-foreground",
                  )}
                >
                  {step.done && <CheckIcon className="size-3" />}
                  <span className="sr-only">{step.done ? "Done:" : "To do:"}</span>
                </span>
                <span className="grid min-w-0 flex-1 gap-0.5">
                  <span className={cn("text-sm font-medium", step.done && "text-muted-foreground line-through decoration-muted-foreground/40")}>
                    {step.title}
                  </span>
                  <span className="text-xs text-muted-foreground">{step.detail}</span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

function TopTrends({ trends }: { trends: TopTrend[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Top opportunities</CardTitle>
        <CardDescription>The best-scoring trends from the last week.</CardDescription>
      </CardHeader>
      <CardContent>
        <ol className="grid gap-1">
          {trends.map((trend) => (
            <li key={trend.id}>
              <Link
                href={`/trends/${trend.id}`}
                className="-mx-2 flex items-center gap-3 rounded-lg p-2 transition-colors hover:bg-primary/5"
              >
                <Score score={trend.opportunity_score} size="sm" />
                <span className="grid min-w-0 flex-1 gap-0.5">
                  <span className="truncate text-sm font-medium">{trend.topic}</span>
                  <span className="truncate text-xs text-muted-foreground">
                    {trend.sources.map(sourceName).join(" · ")} · {trend.mention_count} mention
                    {trend.mention_count === 1 ? "" : "s"}
                  </span>
                </span>
                <ArrowRightIcon className="size-4 text-muted-foreground" />
              </Link>
            </li>
          ))}
        </ol>
        <Link href="/trends" className="mt-3 inline-block text-sm font-medium underline-offset-4 hover:underline">
          See all trends
        </Link>
      </CardContent>
    </Card>
  );
}
