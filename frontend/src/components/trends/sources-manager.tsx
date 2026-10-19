"use client";

import {
  ArrowLeftIcon,
  ChevronDownIcon,
  ExternalLinkIcon,
  RadarIcon,
  SlidersHorizontalIcon,
  TriangleAlertIcon,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { SourceListEditor } from "@/components/trends/source-list-editor";
import { SourceLogo } from "@/components/trends/source-logos";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useToggleSource, useTrendSources } from "@/hooks/use-trends";
import { errorMessage } from "@/lib/api";
import { useCan } from "@/lib/auth";
import { formatDateTime, timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { TrendSourceInfo } from "@/types/api";

// ids must not contain spaces: aria-labelledby splits on whitespace.
const slug = (text: string) => text.toLowerCase().replace(/[^a-z0-9]+/g, "-");

/** One line per source for the list; the full description sits in Details. */
const TAGLINES: Record<string, string> = {
  google_trends: "Popularity and search-interest trends",
  google_trends_tech: "Search-interest trends in technology",
  google_news: "News stories and current events",
  hacker_news: "Tech community discussions and launches",
  reddit: "Community discussions and emerging topics",
  rss: "Industry blogs and publications you follow",
  newsapi: "Headlines from 80,000+ publishers",
  gnews: "Global news headlines by keyword",
  world_news: "Worldwide news by language and country",
  newsdata: "Recent global news by keyword",
  the_news_api: "Worldwide news from 40,000+ publishers",
  exa: "Semantic web search for your keywords",
  serpapi_news: "Structured Google News search results",
  apitube_news: "Real-time news with topic metadata",
  x: "What people are posting about right now",
  instagram: "Top posts for hashtags you track",
  linkedin: "Trending professional conversations",
};

export function sourceStatus(source: TrendSourceInfo): { label: string; tone: string } {
  if (source.pricing === "unavailable")
    return { label: "Unavailable", tone: "bg-muted-foreground/40" };
  if (!source.configured) return { label: "Needs setup", tone: "bg-warning" };
  if (!source.enabled) return { label: "Off", tone: "bg-muted-foreground/40" };
  switch (source.health) {
    case "healthy":
      return { label: "Working", tone: "bg-success" };
    case "rate_limited":
      return { label: "Rate limited", tone: "bg-warning" };
    case "degraded":
      return { label: "Having trouble", tone: "bg-warning" };
    case "down":
      return { label: "Failing", tone: "bg-destructive" };
    default:
      return { label: "Not run yet", tone: "bg-primary/60" };
  }
}

export function SourcesManager() {
  const sources = useTrendSources();
  const toggle = useToggleSource();
  const can = useCan();
  const canManage = can("trends.manage");
  const canEditLists = can("organization.write");
  const [announcement, setAnnouncement] = useState("");

  const groups = sources.data
    ? [
        { title: "Ready to use", items: sources.data.filter((s) => s.configured) },
        {
          title: "Needs setup",
          items: sources.data.filter((s) => !s.configured && s.pricing !== "unavailable"),
        },
        {
          title: "Not available",
          items: sources.data.filter((s) => s.pricing === "unavailable"),
        },
      ].filter((g) => g.items.length)
    : [];

  const onToggle = (source: TrendSourceInfo, enabled: boolean) => {
    setAnnouncement(`Saving ${source.name}…`);
    toggle.mutate(
      { key: source.key, enabled },
      {
        onSuccess: () => {
          const done = `${source.name} ${enabled ? "turned on" : "turned off"} for your discovery feed`;
          setAnnouncement(done);
          toast.success(done);
        },
        onError: (e) => {
          const message = `Couldn't update ${source.name}: ${errorMessage(e)}`;
          setAnnouncement(message);
          toast.error(message);
        },
      },
    );
  };

  return (
    <>
      <Link
        href="/trends"
        className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeftIcon className="size-4" />
        Trends
      </Link>
      {/* Screen readers hear save results without moving focus. */}
      <p className="sr-only" role="status" aria-live="polite">
        {announcement}
      </p>
      <Card className="max-w-3xl">
        <CardContent className="grid gap-0 px-4 sm:px-5">
          <header className="flex items-start gap-3 pb-5">
            <span
              className="grid size-10 shrink-0 place-items-center rounded-lg bg-muted text-foreground"
              aria-hidden
            >
              <SlidersHorizontalIcon className="size-5" />
            </span>
            <div className="grid gap-1 pt-0.5">
              <h1 className="text-lg font-semibold leading-tight">Discovery Sources</h1>
              <p className="text-sm text-muted-foreground">
                Choose which sources contribute trends to your discovery feed.
              </p>
            </div>
          </header>

          {sources.isError && !sources.data ? (
            <Alert variant="destructive" className="mt-5">
              <TriangleAlertIcon aria-hidden />
              <AlertTitle>Couldn&apos;t load sources</AlertTitle>
              <AlertDescription className="grid gap-2">
                <span>{errorMessage(sources.error)}</span>
                <Button
                  variant="outline"
                  size="sm"
                  className="w-fit"
                  onClick={() => sources.refetch()}
                  disabled={sources.isFetching}
                >
                  {sources.isFetching ? "Retrying…" : "Try again"}
                </Button>
              </AlertDescription>
            </Alert>
          ) : !sources.data ? (
            <div className="grid gap-4 border-t pt-5" aria-busy="true" aria-label="Loading sources">
              {Array.from({ length: 4 }, (_, i) => (
                <div key={i} className="flex items-center gap-3">
                  <Skeleton className="size-11 rounded-lg" />
                  <div className="grid flex-1 gap-1.5">
                    <Skeleton className="h-4 w-32" />
                    <Skeleton className="h-3 w-56" />
                  </div>
                  <Skeleton className="h-6 w-16 rounded-full" />
                </div>
              ))}
            </div>
          ) : sources.data.length === 0 ? (
            <div className="grid justify-items-center gap-2 border-t py-10 text-center">
              <RadarIcon className="size-6 text-muted-foreground" aria-hidden />
              <p className="font-medium">No sources available</p>
              <p className="max-w-md text-sm text-muted-foreground">
                This server doesn&apos;t offer any trend sources yet. Ask your ContentPulse
                administrator to set some up.
              </p>
            </div>
          ) : (
            groups.map((group) => (
              <section
                key={group.title}
                aria-labelledby={`group-${slug(group.title)}`}
                className="border-t pt-4 pb-2"
              >
                <h2
                  id={`group-${slug(group.title)}`}
                  className="mb-1 text-xs font-medium tracking-wide text-muted-foreground uppercase"
                >
                  {group.title}
                </h2>
                <ul className="grid">
                  {group.items.map((source) => (
                    <SourceRow
                      key={source.key}
                      source={source}
                      canManage={canManage}
                      canEditLists={canEditLists}
                      pending={toggle.isPending && toggle.variables?.key === source.key}
                      onToggle={(enabled) => onToggle(source, enabled)}
                    />
                  ))}
                </ul>
              </section>
            ))
          )}

          <p className="border-t pt-4 text-xs text-muted-foreground">
            Turning a source off only changes your organization&apos;s discovery feed; it
            doesn&apos;t stop global collection or affect other organizations. Provider keys,
            schedules and quotas stay managed by ContentPulse.
            {canManage
              ? " Select a status to turn a source on or off."
              : " Only admins can change these settings."}
          </p>
        </CardContent>
      </Card>
    </>
  );
}

function StatusPill({
  source,
  canManage,
  pending,
  descriptionId,
  onToggle,
}: {
  source: TrendSourceInfo;
  canManage: boolean;
  pending: boolean;
  descriptionId: string;
  onToggle: (enabled: boolean) => void;
}) {
  const base =
    "inline-flex h-7 min-w-20 items-center justify-center rounded-full border px-3 text-xs font-medium whitespace-nowrap";
  if (source.pricing === "unavailable") {
    return (
      <span className={cn(base, "border-dashed text-muted-foreground")}>Unavailable</span>
    );
  }
  const tone = source.enabled
    ? "border-success/30 bg-success/10 text-[color-mix(in_oklch,var(--color-success)_65%,var(--color-foreground))]"
    : "border-border bg-muted text-muted-foreground";
  const label = pending ? "Saving…" : source.enabled ? "Enabled" : "Disabled";
  if (!canManage) return <span className={cn(base, tone)}>{label}</span>;
  return (
    <button
      type="button"
      role="switch"
      aria-checked={source.enabled}
      aria-label={`Include ${source.name} in discovery feed`}
      aria-describedby={descriptionId}
      aria-busy={pending || undefined}
      disabled={pending}
      title={source.enabled ? "Turn off for your feed" : "Turn on for your feed"}
      onClick={() => onToggle(!source.enabled)}
      // 44px tall hit area around the 28px pill.
      className={cn(
        base,
        tone,
        "relative cursor-pointer transition-colors outline-none before:absolute before:-inset-y-2 before:inset-x-0 hover:brightness-95 focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-wait disabled:opacity-70",
      )}
    >
      {label}
    </button>
  );
}

function SourceRow({
  source,
  canManage,
  canEditLists,
  pending,
  onToggle,
}: {
  source: TrendSourceInfo;
  canManage: boolean;
  canEditLists: boolean;
  pending: boolean;
  onToggle: (enabled: boolean) => void;
}) {
  const s = sourceStatus(source);
  const unavailable = source.pricing === "unavailable";
  const descriptionId = `source-${slug(source.key)}-description`;
  const unhealthy =
    source.enabled &&
    source.configured &&
    ["rate_limited", "degraded", "down"].includes(source.health);
  const listField =
    source.key === "reddit" ? "subreddits" : source.key === "rss" ? "rss_feeds" : null;
  const [open, setOpen] = useState(false);
  const panelId = `source-${slug(source.key)}-details`;

  return (
    <li className="grid gap-2 py-2.5">
      <div className="flex items-center gap-3">
        <span
          className="grid size-11 shrink-0 place-items-center rounded-lg border bg-white shadow-xs"
          aria-hidden
        >
          <SourceLogo sourceKey={source.key} />
        </span>
        <div className="grid min-w-0 flex-1 gap-0.5">
          <h3 className={cn("font-medium leading-snug", unavailable && "text-muted-foreground")}>
            {source.name}
          </h3>
          <p id={descriptionId} className="text-sm text-muted-foreground">
            {TAGLINES[source.key] ?? source.description}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <StatusPill
            source={source}
            canManage={canManage}
            pending={pending}
            descriptionId={descriptionId}
            onToggle={onToggle}
          />
          <Button
            variant="ghost"
            size="icon"
            className="text-muted-foreground"
            aria-expanded={open}
            aria-controls={panelId}
            aria-label={listField ? `${source.name} settings` : `${source.name} details`}
            title={listField ? "Settings" : "Details"}
            onClick={() => setOpen((v) => !v)}
          >
            <ChevronDownIcon className={cn("transition-transform", open && "rotate-180")} />
          </Button>
        </div>
      </div>

      {(source.missing.length > 0 || unhealthy) && (
        <div className="ml-14 grid gap-1">
          {source.missing.length > 0 && (
            <p className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
              <span className="size-1.5 rounded-full bg-warning" aria-hidden />
              {source.enabled ? "Skipped until set up on the server:" : "Set on the server:"}
              {source.missing.map((v) => (
                <code key={v} className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">
                  {v}
                </code>
              ))}
            </p>
          )}
          {unhealthy && (
            <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <span className={cn("size-1.5 rounded-full", s.tone)} aria-hidden />
              {s.label}
              {source.last_error && `: ${source.last_error}`}
              {source.last_failure_at && ` (${timeAgo(source.last_failure_at)})`}
            </p>
          )}
        </div>
      )}

      {open && (
        <div
          id={panelId}
          className="ml-14 grid gap-2 rounded-lg bg-muted/50 p-3 text-xs text-muted-foreground"
        >
          <p className="text-sm">{source.description}</p>
          {listField && <SourceListEditor field={listField} canEdit={canEditLists} />}
          {source.note && <p>{source.note}</p>}
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
            <span>
              {source.last_success_at ? (
                <>
                  Last success{" "}
                  <time title={formatDateTime(source.last_success_at)}>
                    {timeAgo(source.last_success_at)}
                  </time>
                </>
              ) : (
                "No successful runs yet"
              )}
            </span>
            {source.docs_url && (
              <a
                href={source.docs_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 underline-offset-4 hover:text-foreground hover:underline"
              >
                Docs <ExternalLinkIcon className="size-3" />
              </a>
            )}
          </div>
        </div>
      )}
    </li>
  );
}
